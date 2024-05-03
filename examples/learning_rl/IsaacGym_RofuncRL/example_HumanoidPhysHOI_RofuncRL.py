"""
HumanoidPhysHOI (RofuncRL)
===========================

Humanoid backflip/walk/run/dance/hop, trained by RofuncRL
"""

import isaacgym
import argparse

from rofunc.config.utils import omegaconf_to_dict, get_config
from rofunc.learning.RofuncRL.tasks import Tasks
from rofunc.learning.RofuncRL.trainers import Trainers
from rofunc.learning.pre_trained_models.download import model_zoo
from rofunc.learning.utils.utils import set_seed


def train(custom_args):
    # Config task and trainer parameters for Isaac Gym environments
    args_overrides = ["task={}".format(custom_args.task),
                      "train={}{}RofuncRL".format(custom_args.task, custom_args.agent.upper()),
                      "device_id={}".format(custom_args.sim_device),
                      "rl_device=cuda:{}".format(custom_args.rl_device),
                      "headless={}".format(custom_args.headless),
                      "num_envs={}".format(custom_args.num_envs)]
    cfg = get_config('./learning/rl', 'config', args=args_overrides)
    cfg.task.env.motion_file = custom_args.motion_file
    if custom_args.debug == "True":
        cfg.train.Trainer.wandb = False
    cfg_dict = omegaconf_to_dict(cfg.task)

    set_seed(cfg.train.Trainer.seed)

    # Instantiate the Isaac Gym environment
    env = Tasks().task_map[custom_args.task](cfg=cfg_dict,
                                             rl_device=cfg.rl_device,
                                             sim_device=f'cuda:{cfg.device_id}',
                                             graphics_device_id=cfg.device_id,
                                             headless=cfg.headless,
                                             virtual_screen_capture=cfg.capture_video,  # TODO: check
                                             force_render=cfg.force_render)

    # Instantiate the RL trainer
    trainer = Trainers().trainer_map[custom_args.agent](cfg=cfg,
                                                        env=env,
                                                        device=cfg.rl_device,
                                                        env_name=custom_args.task)
    if custom_args.ckpt_path is not None:
        trainer.agent.load_ckpt(custom_args.ckpt_path)
    # Start training
    trainer.train()


def inference(custom_args):
    # Config task and trainer parameters for Isaac Gym environments
    args_overrides = ["task={}".format(custom_args.task),
                      "train={}{}RofuncRL".format(custom_args.task, custom_args.agent.upper()),
                      "device_id={}".format(custom_args.sim_device),
                      "rl_device=cuda:{}".format(custom_args.rl_device),
                      "headless={}".format(False),
                      "num_envs={}".format(16)]
    cfg = get_config('./learning/rl', 'config', args=args_overrides)
    cfg.task.env.motion_file = custom_args.motion_file
    cfg_dict = omegaconf_to_dict(cfg.task)

    set_seed(cfg.train.Trainer.seed)

    # Instantiate the Isaac Gym environment
    infer_env = Tasks().task_map[custom_args.task](cfg=cfg_dict,
                                       rl_device=cfg.rl_device,
                                       sim_device=f'cuda:{cfg.device_id}',
                                       graphics_device_id=cfg.device_id,
                                       headless=cfg.headless,
                                       virtual_screen_capture=cfg.capture_video,  # TODO: check
                                       force_render=cfg.force_render)

    # Instantiate the RL trainer
    trainer = Trainers().trainer_map[custom_args.agent](cfg=cfg,
                                                        env=infer_env,
                                                        device=cfg.rl_device,
                                                        env_name=custom_args.task,
                                                        inference=True)

    # load checkpoint
    if custom_args.ckpt_path is None:
        custom_args.ckpt_path = model_zoo(name=f"{custom_args.task}.pth")
    trainer.agent.load_ckpt(custom_args.ckpt_path)

    # Start inference
    trainer.inference()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    # Available tasks: HumanoidPhyshoi
    parser.add_argument("--task", type=str, default="HumanoidPhysHOI")
    # Available motion files: backdribble, backspin, changeleg, fingerspin, pass, rebound, toss, walkpick
    parser.add_argument("--motion_file", type=str, default="examples/data/ballplay/walkpick.pt")
    # Available agent: physhoi
    parser.add_argument("--agent", type=str, default="physhoi")  # ppo, physhoi
    parser.add_argument("--num_envs", type=int, default=2048)
    parser.add_argument("--sim_device", type=int, default=1)
    parser.add_argument("--rl_device", type=int, default=1)
    parser.add_argument("--headless", type=str, default="True")
    parser.add_argument("--inference", action="store_true", help="turn to inference mode while adding this argument")
    parser.add_argument("--ckpt_path", type=str, default="/home/ubuntu/Github/Xianova_Robotics/Rofunc-secret/examples/learning_rl/IsaacGym_RofuncRL/runs/RofuncRL_PhysHOITrainer_HumanoidPhysHOI_24-04-23_18-21-03-579079/checkpoints/best_ckpt.pth")
    parser.add_argument("--debug", type=str, default="False")
    custom_args = parser.parse_args()

    if not custom_args.inference:
        train(custom_args)
    else:
        inference(custom_args)
