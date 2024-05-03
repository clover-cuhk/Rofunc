"""
Humanoid Motion View (RofuncRL)
===========================

Preview the motion of the digital humanoid
"""

import isaacgym
import argparse
from omegaconf import OmegaConf

from rofunc.config.utils import omegaconf_to_dict, get_config, get_view_motion_config
from rofunc.learning.RofuncRL.tasks import Tasks
from rofunc.learning.RofuncRL.trainers import Trainers


def inference(custom_args):
    args_overrides = [
        f"task={custom_args.task}",
        "train=HumanoidHOTUViewMotionRofuncRL",
        f"device_id=0",
        f"rl_device=cuda:{gpu_id}",
        "headless={}".format(False),
        "num_envs={}".format(1),
    ]
    cfg = get_config("./learning/rl", "config", args=args_overrides)
    cfg_view_motion = get_view_motion_config(custom_args.view_motion_type)
    cfg.task.env = OmegaConf.merge(cfg.task.env, cfg_view_motion)
    cfg_dict = omegaconf_to_dict(cfg.task)

    # Instantiate the Isaac Gym environment
    infer_env = Tasks().task_map[custom_args.task](cfg=cfg_dict,
                                                   rl_device=cfg.rl_device,
                                                   sim_device=f'cuda:{cfg.device_id}',
                                                   graphics_device_id=cfg.device_id,
                                                   headless=cfg.headless,
                                                   virtual_screen_capture=cfg.capture_video,  # TODO: check
                                                   force_render=cfg.force_render)

    # Instantiate the RL trainer
    trainer = Trainers().trainer_map["ase"](cfg=cfg,
                                            env=infer_env,
                                            device=cfg.rl_device,
                                            env_name=custom_args.task,
                                            hrl=False,
                                            inference=True)

    # Start inference
    trainer.inference()


if __name__ == "__main__":
    gpu_id = 0

    parser = argparse.ArgumentParser()
    # Find or define your own config in `rofunc/config/`
    parser.add_argument("--task", type=str, default="HumanoidHOTUViewMotion")
    # Available types of asset file path:
    #  1. HOTUHumanoid
    #  2. HOTUHumanoidWQbhand
    #  3. HOTUH1WQbhand
    #  4. HOTUCURIWQbhand
    #  5. HOTUWalker
    parser.add_argument("--view_motion_type", type=str, default="HOTUH1WQbhand")
    custom_args = parser.parse_args()

    inference(custom_args)
