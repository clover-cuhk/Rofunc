# Copyright 2023, Junjia LIU, jjliu@mae.cuhk.edu.hk
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Callable, Union, Tuple, Optional

import gym
import gymnasium
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from hydra.core.global_hydra import GlobalHydra
from omegaconf import DictConfig

import rofunc as rf
from rofunc.config.utils import get_config
from rofunc.learning.RofuncRL.agents.base_agent import BaseAgent
from rofunc.learning.RofuncRL.agents.mixline.amp_agent import AMPAgent
from rofunc.learning.RofuncRL.utils.memory import Memory
from rofunc.learning.RofuncRL.utils.memory import RandomMemory
from rofunc.learning.pre_trained_models.download import model_zoo
from .hotu_llc_agent import HOTULLCAgent


class HOTUHLMMAgent(AMPAgent):
    """
    HOTU - Human large Language-Manipulation Model (HLMM) agent for learning manipulation skills from human demonstrations
    """
    def __init__(self,
                 cfg: DictConfig,
                 observation_space: Optional[Union[int, Tuple[int], gym.Space, gymnasium.Space]],
                 action_space: Optional[Union[int, Tuple[int], gym.Space, gymnasium.Space]],
                 memory: Optional[Union[Memory, Tuple[Memory]]] = None,
                 device: Optional[Union[str, torch.device]] = None,
                 experiment_dir: Optional[str] = None,
                 rofunc_logger: Optional[rf.logger.BeautyLogger] = None,
                 amp_observation_space: Optional[Union[int, Tuple[int], gym.Space, gymnasium.Space]] = None,
                 motion_dataset: Optional[Union[Memory, Tuple[Memory]]] = None,
                 replay_buffer: Optional[Union[Memory, Tuple[Memory]]] = None,
                 collect_reference_motions: Optional[Callable[[int], torch.Tensor]] = None,
                 task_related_state_size: Optional[int] = None, ):
        """
        :param cfg: Configuration
        :param observation_space: Observation space
        :param action_space: Action space
        :param memory: Memory for storing transitions
        :param device: Device on which the torch tensor is allocated
        :param experiment_dir: Directory where experiment outputs are saved
        :param rofunc_logger: Rofunc logger
        :param amp_observation_space: cfg["env"]["numASEObsSteps"] * NUM_ASE_OBS_PER_STEP
        :param motion_dataset: Motion dataset
        :param replay_buffer: Replay buffer
        :param collect_reference_motions: Function for collecting reference motions
        :param task_related_state_size: Size of task-related states
        """
        """ASE specific parameters"""
        self._ase_latent_dim = cfg.Agent.ase_latent_dim
        self._task_related_state_size = task_related_state_size
        super().__init__(cfg, observation_space, self._ase_latent_dim, memory, device,
                         experiment_dir, rofunc_logger, amp_observation_space, motion_dataset, replay_buffer,
                         collect_reference_motions)

        '''Create HLMM-specific tensors in memory except for AMP'''
        if hasattr(cfg.Model, "state_encoder"):
            img_channel = int(self.cfg.Model.state_encoder.inp_channels)
            img_size = int(self.cfg.Model.state_encoder.image_size)
            state_tensor_size = (img_channel, img_size, img_size)
            kd = True
        else:
            state_tensor_size = observation_space
            kd = False

        # Override the state/next state/action size
        self.memory.create_tensor(name="states", size=state_tensor_size, dtype=torch.float32, keep_dimensions=kd)
        self.memory.create_tensor(name="next_states", size=state_tensor_size, dtype=torch.float32, keep_dimensions=kd)
        self.memory.create_tensor(name="actions", size=action_space, dtype=torch.float32)
        # Add two more tensors for storing omega actions and discriminator rewards
        self.memory.create_tensor(name="omega_actions", size=self._ase_latent_dim, dtype=torch.float32)
        self.memory.create_tensor(name="disc_rewards", size=1, dtype=torch.float32)
        self._tensors_names.append("omega_actions")
        self._tensors_names.append("disc_rewards")

        '''Get hyper-parameters from config'''
        self._task_reward_weight = self.cfg.Agent.task_reward_weight
        self._style_reward_weight = self.cfg.Agent.style_reward_weight
        self._demo_style_reward_weight = self.cfg.Agent.demo_style_reward_weight
        self._rewards_shaper = None
        # self._rewards_shaper = self.cfg.get("Agent", {}).get("rewards_shaper", lambda rewards: rewards * 0.01)

        """Define pre-trained low-level controller"""
        GlobalHydra.instance().clear()
        args_overrides = ["task=HumanoidHOTUGetup", "train=HumanoidHOTUGetupHOTURofuncRL"]
        self.llc_config = get_config(absl_config_path='/home/ubuntu/Github/HOTU/hotu/configs', config_name='config',
                                     args=args_overrides)
        if self.cfg.Agent.llc_ckpt_path is None:
            llc_ckpt_path = model_zoo(name="HumanoidASEGetupSwordShield.pth")
        else:
            llc_ckpt_path = self.cfg.Agent.llc_ckpt_path
        llc_observation_space = gym.spaces.Box(low=-np.inf, high=np.inf,
                                               shape=(observation_space.shape[0] - self._task_related_state_size,))
        llc_memory = RandomMemory(memory_size=self.memory.memory_size, num_envs=self.memory.num_envs, device=device)
        self.llc_agent = HOTULLCAgent(self.llc_config.train, llc_observation_space, action_space, llc_memory, device,
                                      experiment_dir, rofunc_logger, amp_observation_space,
                                      motion_dataset, replay_buffer, collect_reference_motions)
        self.llc_agent.load_ckpt(llc_ckpt_path)

        '''Misc variables'''
        self._current_states = None
        self._current_log_prob = None
        self._current_next_states = None
        self._llc_step = 0
        self._omega_actions_for_llc = None
        self.pre_states = None
        self.llc_cum_rew = torch.zeros((self.memory.num_envs, 1), dtype=torch.float32).to(self.device)
        self.llc_cum_disc_rew = torch.zeros((self.memory.num_envs, 1), dtype=torch.float32).to(self.device)
        self.need_reset = torch.zeros((self.memory.num_envs, 1), dtype=torch.float32).to(self.device)
        self.need_terminate = torch.zeros((self.memory.num_envs, 1), dtype=torch.float32).to(self.device)

    def _get_llc_action(self, states: torch.Tensor, omega_actions: torch.Tensor):
        # get actions from low-level controller
        task_agnostic_states = states[:, :states.shape[1] - self._task_related_state_size]
        z = torch.nn.functional.normalize(omega_actions, dim=-1)
        actions, _ = self.llc_agent.act(task_agnostic_states, deterministic=False, ase_latents=z)
        return actions

    def act(self, states: torch.Tensor, deterministic: bool = False):
        if self._current_states is not None:
            states = self._current_states
        self.pre_states = states
        self.llc_cum_rew = torch.zeros((self.memory.num_envs, 1), dtype=torch.float32).to(self.device)
        self.llc_cum_disc_rew = torch.zeros((self.memory.num_envs, 1), dtype=torch.float32).to(self.device)
        self.need_reset = torch.zeros((self.memory.num_envs, 1), dtype=torch.float32).to(self.device)
        self.need_terminate = torch.zeros((self.memory.num_envs, 1), dtype=torch.float32).to(self.device)
        omega_actions, self._current_log_prob = self.policy(self._state_preprocessor(states),
                                                            deterministic=deterministic)
        self._omega_actions_for_llc = omega_actions
        actions = self._get_llc_action(states, self._omega_actions_for_llc)
        return actions, self._current_log_prob

    def _get_llc_disc_reward(self, amp_states):
        with torch.no_grad():
            amp_logits = self.llc_agent.discriminator(self.llc_agent._amp_state_preprocessor(amp_states))
            if self.llc_agent._least_square_discriminator:
                style_rewards = torch.maximum(torch.tensor(1 - 0.25 * torch.square(1 - amp_logits)),
                                              torch.tensor(0.0001, device=self.device))
            else:
                style_rewards = -torch.log(torch.maximum(torch.tensor(1 - 1 / (1 + torch.exp(-amp_logits))),
                                                         torch.tensor(0.0001, device=self.device)))
            style_rewards *= self.llc_agent._discriminator_reward_scale
        return style_rewards

    def store_transition(self, states: torch.Tensor, actions: torch.Tensor, next_states: torch.Tensor,
                         rewards: torch.Tensor, terminated: torch.Tensor, truncated: torch.Tensor, infos: torch.Tensor):
        if self._current_states is not None:
            states = self._current_states

        BaseAgent.store_transition(self, states=states, actions=actions, next_states=next_states,
                                   rewards=rewards, terminated=terminated, truncated=truncated, infos=infos)

        amp_states = infos["amp_obs"]

        # reward shaping
        if self._rewards_shaper is not None:
            rewards = self._rewards_shaper(rewards)

        # compute values
        # values = self.value(self._state_preprocessor(self.pre_states))
        values = self.value(self._state_preprocessor(states))
        values = self._value_preprocessor(values, inverse=True)
        if (values.isnan() == True).any():
            print("values is nan")

        next_values = self.value(self._state_preprocessor(next_states))
        next_values = self._value_preprocessor(next_values, inverse=True)
        next_values *= self.need_terminate.logical_not()

        # storage transition in memory
        self.memory.add_samples(states=states, actions=actions,
                                rewards=rewards,
                                next_states=next_states,
                                terminated=terminated, truncated=truncated, log_prob=self._current_log_prob,
                                values=values, amp_states=amp_states, next_values=next_values,
                                omega_actions=self._omega_actions_for_llc,
                                disc_rewards=self._get_llc_disc_reward(amp_states))

    def update_net(self):
        """
        Update the network
        """
        # update dataset of reference motions
        self.motion_dataset.add_samples(states=self.collect_reference_motions(self._amp_batch_size))

        '''Compute combined rewards'''
        rewards = self.memory.get_tensor_by_name("rewards")
        amp_states = self.memory.get_tensor_by_name("amp_states")
        style_rewards = self.memory.get_tensor_by_name("disc_rewards")

        with torch.no_grad():
            # Compute style reward from discriminator
            amp_logits = self.discriminator(self._amp_state_preprocessor(amp_states))
            if self._least_square_discriminator:
                demo_style_rewards = torch.maximum(torch.tensor(1 - 0.25 * torch.square(1 - amp_logits)),
                                                   torch.tensor(0.0001, device=self.device))
            else:
                demo_style_rewards = -torch.log(torch.maximum(torch.tensor(1 - 1 / (1 + torch.exp(-amp_logits))),
                                                              torch.tensor(0.0001, device=self.device)))
        demo_style_rewards *= self._discriminator_reward_scale

        combined_rewards = (self._task_reward_weight * rewards
                            + self._style_reward_weight * style_rewards
                            + self._demo_style_reward_weight * demo_style_rewards)

        '''Compute Generalized Advantage Estimator (GAE)'''
        values = self.memory.get_tensor_by_name("values")
        next_values = self.memory.get_tensor_by_name("next_values")
        if (values.isnan() == True).any():
            print("values is nan")

        advantage = 0
        advantages = torch.zeros_like(combined_rewards)
        not_dones = self.memory.get_tensor_by_name("terminated").logical_not()
        memory_size = combined_rewards.shape[0]

        # advantages computation
        for i in reversed(range(memory_size)):
            advantage = combined_rewards[i] - values[i] + self._discount * (
                    next_values[i] + self._td_lambda * not_dones[i] * advantage)
            advantages[i] = advantage
        # returns computation
        values_target = advantages + values
        # advantage normalization
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        self.memory.set_tensor_by_name("values", self._value_preprocessor(values, train=True))
        self.memory.set_tensor_by_name("returns", self._value_preprocessor(values_target, train=True))
        self.memory.set_tensor_by_name("advantages", advantages)

        '''Sample mini-batches from memory and update the network'''
        sampled_batches = self.memory.sample_all(names=self._tensors_names, mini_batches=self._mini_batch_size)
        sampled_motion_batches = self.motion_dataset.sample(names=["states"],
                                                            batch_size=self.memory.memory_size * self.memory.num_envs,
                                                            mini_batches=self._mini_batch_size)

        if len(self.replay_buffer):
            sampled_replay_batches = self.replay_buffer.sample(names=["states"],
                                                               batch_size=self.memory.memory_size * self.memory.num_envs,
                                                               mini_batches=self._mini_batch_size)
        else:
            sampled_replay_batches = [[batches[self._tensors_names.index("amp_states")]] for batches in sampled_batches]

        cumulative_policy_loss = 0
        cumulative_entropy_loss = 0
        cumulative_value_loss = 0
        cumulative_discriminator_loss = 0

        # learning epochs
        for epoch in range(self._learning_epochs):
            # mini-batches loop
            for i, (sampled_states, sampled_actions, sampled_rewards, samples_next_states, samples_terminated,
                    sampled_log_prob, sampled_values, sampled_returns, sampled_advantages, sampled_amp_states,
                    _, sampled_omega_actions, _) in enumerate(sampled_batches):
                sampled_states = self._state_preprocessor(sampled_states, train=True)
                _, log_prob_now = self.policy(sampled_states, sampled_omega_actions)

                # compute entropy loss
                entropy_loss = -self._entropy_loss_scale * self.policy.get_entropy().mean()

                # compute policy loss
                ratio = torch.exp(log_prob_now - sampled_log_prob)
                surrogate = sampled_advantages * ratio
                surrogate_clipped = sampled_advantages * torch.clip(ratio, 1.0 - self._ratio_clip,
                                                                    1.0 + self._ratio_clip)

                policy_loss = -torch.min(surrogate, surrogate_clipped).mean()

                # compute value loss
                predicted_values = self.value(sampled_states)

                if self._clip_predicted_values:
                    predicted_values = sampled_values + torch.clip(predicted_values - sampled_values,
                                                                   min=-self._value_clip,
                                                                   max=self._value_clip)
                value_loss = self._value_loss_scale * F.mse_loss(sampled_returns, predicted_values)

                # compute discriminator loss
                if self._discriminator_batch_size:
                    sampled_amp_states_batch = self._amp_state_preprocessor(
                        sampled_amp_states[0:self._discriminator_batch_size], train=True)
                    sampled_amp_replay_states = self._amp_state_preprocessor(
                        sampled_replay_batches[i][0][0:self._discriminator_batch_size], train=True)
                    sampled_amp_motion_states = self._amp_state_preprocessor(
                        sampled_motion_batches[i][0][0:self._discriminator_batch_size], train=True)
                else:
                    sampled_amp_states_batch = self._amp_state_preprocessor(sampled_amp_states, train=True)
                    sampled_amp_replay_states = self._amp_state_preprocessor(sampled_replay_batches[i][0], train=True)
                    sampled_amp_motion_states = self._amp_state_preprocessor(sampled_motion_batches[i][0], train=True)

                sampled_amp_motion_states.requires_grad_(True)
                amp_logits = self.discriminator(sampled_amp_states_batch)
                amp_replay_logits = self.discriminator(sampled_amp_replay_states)
                amp_motion_logits = self.discriminator(sampled_amp_motion_states)
                amp_cat_logits = torch.cat([amp_logits, amp_replay_logits], dim=0)

                # discriminator prediction loss
                if self._least_square_discriminator:
                    discriminator_loss = 0.5 * (
                            F.mse_loss(amp_cat_logits, -torch.ones_like(amp_cat_logits), reduction='mean') \
                            + F.mse_loss(amp_motion_logits, torch.ones_like(amp_motion_logits), reduction='mean'))
                else:
                    discriminator_loss = 0.5 * (nn.BCEWithLogitsLoss()(amp_cat_logits, torch.zeros_like(amp_cat_logits)) \
                                                + nn.BCEWithLogitsLoss()(amp_motion_logits,
                                                                         torch.ones_like(amp_motion_logits)))

                # discriminator logit regularization
                if self._discriminator_logit_regularization_scale:
                    logit_weights = torch.flatten(list(self.discriminator.modules())[-1].weight)
                    discriminator_loss += self._discriminator_logit_regularization_scale * torch.sum(
                        torch.square(logit_weights))

                # discriminator gradient penalty
                if self._discriminator_gradient_penalty_scale:
                    amp_motion_gradient = torch.autograd.grad(amp_motion_logits,
                                                              sampled_amp_motion_states,
                                                              grad_outputs=torch.ones_like(amp_motion_logits),
                                                              create_graph=True,
                                                              retain_graph=True,
                                                              only_inputs=True)
                    gradient_penalty = torch.sum(torch.square(amp_motion_gradient[0]), dim=-1).mean()
                    discriminator_loss += self._discriminator_gradient_penalty_scale * gradient_penalty

                # discriminator weight decay
                if self._discriminator_weight_decay_scale:
                    weights = [torch.flatten(module.weight) for module in self.discriminator.modules() \
                               if isinstance(module, torch.nn.Linear)]
                    weight_decay = torch.sum(torch.square(torch.cat(weights, dim=-1)))
                    discriminator_loss += self._discriminator_weight_decay_scale * weight_decay

                discriminator_loss *= self._discriminator_loss_scale

                '''Update networks'''
                # Update policy network
                self.optimizer_policy.zero_grad()
                (policy_loss + entropy_loss).backward()
                if self._grad_norm_clip > 0:
                    nn.utils.clip_grad_norm_(self.policy.parameters(), self._grad_norm_clip)
                self.optimizer_policy.step()

                # Update value network
                self.optimizer_value.zero_grad()
                value_loss.backward()
                if self._grad_norm_clip > 0:
                    nn.utils.clip_grad_norm_(self.value.parameters(), self._grad_norm_clip)
                self.optimizer_value.step()

                # Update discriminator network
                self.optimizer_disc.zero_grad()
                discriminator_loss.backward()
                if self._grad_norm_clip > 0:
                    nn.utils.clip_grad_norm_(self.discriminator.parameters(), self._grad_norm_clip)
                self.optimizer_disc.step()

                # update cumulative losses
                cumulative_policy_loss += policy_loss.item()
                cumulative_value_loss += value_loss.item()
                if self._entropy_loss_scale:
                    cumulative_entropy_loss += entropy_loss.item()
                cumulative_discriminator_loss += discriminator_loss.item()

            # update learning rate
            if self._lr_scheduler:
                self.scheduler_policy.step()
                self.scheduler_value.step()
                self.scheduler_disc.step()

        # update AMP replay buffer
        self.replay_buffer.add_samples(states=amp_states.view(-1, amp_states.shape[-1]))

        # record data
        self.track_data("Info / Combined rewards", combined_rewards.mean().cpu())
        self.track_data("Info / Style rewards", style_rewards.mean().cpu())
        self.track_data("Info / Task rewards", rewards.mean().cpu())
        self.track_data("Info / Demo style rewards", demo_style_rewards.mean().cpu())

        self.track_data("Loss / Policy loss", cumulative_policy_loss / (self._learning_epochs * self._mini_batch_size))
        self.track_data("Loss / Value loss", cumulative_value_loss / (self._learning_epochs * self._mini_batch_size))
        self.track_data("Loss / Discriminator loss",
                        cumulative_discriminator_loss / (self._learning_epochs * self._mini_batch_size))
        if self._entropy_loss_scale:
            self.track_data("Loss / Entropy loss",
                            cumulative_entropy_loss / (self._learning_epochs * self._mini_batch_size))
        if self._lr_scheduler:
            self.track_data("Learning / Learning rate (policy)", self.scheduler_policy.get_last_lr()[0])
            self.track_data("Learning / Learning rate (value)", self.scheduler_value.get_last_lr()[0])
            self.track_data("Learning / Learning rate (discriminator)", self.scheduler_disc.get_last_lr()[0])