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

"""
Attention: Since the Autodesk FBX SDK just supports Python 3.7, this script should be run with Python 3.7.
"""

import multiprocessing
import os.path
import click
import glob

import numpy as np

import rofunc as rf
from rofunc.utils.datalab.poselib.poselib.core.rotation3d import *
from rofunc.utils.datalab.poselib.poselib.skeleton.skeleton3d import (
    SkeletonState,
    SkeletonMotion,
)
from rofunc.utils.datalab.poselib.poselib.visualization.common import (
    plot_skeleton_motion_interactive,
    plot_skeleton_state,
)


def _project_joints(motion):
    right_upper_arm_id = motion.skeleton_tree._node_indices["right_upper_arm"]
    right_lower_arm_id = motion.skeleton_tree._node_indices["right_lower_arm"]
    right_hand_id = motion.skeleton_tree._node_indices["right_hand"]
    left_upper_arm_id = motion.skeleton_tree._node_indices["left_upper_arm"]
    left_lower_arm_id = motion.skeleton_tree._node_indices["left_lower_arm"]
    left_hand_id = motion.skeleton_tree._node_indices["left_hand"]

    right_thigh_id = motion.skeleton_tree._node_indices["right_thigh"]
    right_shin_id = motion.skeleton_tree._node_indices["right_shin"]
    right_foot_id = motion.skeleton_tree._node_indices["right_foot"]
    left_thigh_id = motion.skeleton_tree._node_indices["left_thigh"]
    left_shin_id = motion.skeleton_tree._node_indices["left_shin"]
    left_foot_id = motion.skeleton_tree._node_indices["left_foot"]

    device = motion.global_translation.device

    # right arm
    right_upper_arm_pos = motion.global_translation[..., right_upper_arm_id, :]
    right_lower_arm_pos = motion.global_translation[..., right_lower_arm_id, :]
    right_hand_pos = motion.global_translation[..., right_hand_id, :]
    right_shoulder_rot = motion.local_rotation[..., right_upper_arm_id, :]
    right_elbow_rot = motion.local_rotation[..., right_lower_arm_id, :]

    right_arm_delta0 = right_upper_arm_pos - right_lower_arm_pos
    right_arm_delta1 = right_hand_pos - right_lower_arm_pos
    right_arm_delta0 = right_arm_delta0 / torch.norm(
        right_arm_delta0, dim=-1, keepdim=True
    )
    right_arm_delta1 = right_arm_delta1 / torch.norm(
        right_arm_delta1, dim=-1, keepdim=True
    )
    right_elbow_dot = torch.sum(-right_arm_delta0 * right_arm_delta1, dim=-1)
    right_elbow_dot = torch.clamp(right_elbow_dot, -1.0, 1.0)
    right_elbow_theta = torch.acos(right_elbow_dot)
    right_elbow_q = quat_from_angle_axis(
        -torch.abs(right_elbow_theta),
        torch.tensor(np.array([[0.0, 1.0, 0.0]]), device=device, dtype=torch.float32),
    )

    right_elbow_local_dir = motion.skeleton_tree.local_translation[right_hand_id]
    right_elbow_local_dir = right_elbow_local_dir / torch.norm(right_elbow_local_dir)
    right_elbow_local_dir_tile = torch.tile(
        right_elbow_local_dir.unsqueeze(0), [right_elbow_rot.shape[0], 1]
    )
    right_elbow_local_dir0 = quat_rotate(right_elbow_rot, right_elbow_local_dir_tile)
    right_elbow_local_dir1 = quat_rotate(right_elbow_q, right_elbow_local_dir_tile)
    right_arm_dot = torch.sum(right_elbow_local_dir0 * right_elbow_local_dir1, dim=-1)
    right_arm_dot = torch.clamp(right_arm_dot, -1.0, 1.0)
    right_arm_theta = torch.acos(right_arm_dot)
    right_arm_theta = torch.where(
        right_elbow_local_dir0[..., 1] <= 0, right_arm_theta, -right_arm_theta
    )
    right_arm_q = quat_from_angle_axis(
        right_arm_theta, right_elbow_local_dir.unsqueeze(0)
    )
    right_shoulder_rot = quat_mul(right_shoulder_rot, right_arm_q)

    # left arm
    left_upper_arm_pos = motion.global_translation[..., left_upper_arm_id, :]
    left_lower_arm_pos = motion.global_translation[..., left_lower_arm_id, :]
    left_hand_pos = motion.global_translation[..., left_hand_id, :]
    left_shoulder_rot = motion.local_rotation[..., left_upper_arm_id, :]
    left_elbow_rot = motion.local_rotation[..., left_lower_arm_id, :]

    left_arm_delta0 = left_upper_arm_pos - left_lower_arm_pos
    left_arm_delta1 = left_hand_pos - left_lower_arm_pos
    left_arm_delta0 = left_arm_delta0 / torch.norm(
        left_arm_delta0, dim=-1, keepdim=True
    )
    left_arm_delta1 = left_arm_delta1 / torch.norm(
        left_arm_delta1, dim=-1, keepdim=True
    )
    left_elbow_dot = torch.sum(-left_arm_delta0 * left_arm_delta1, dim=-1)
    left_elbow_dot = torch.clamp(left_elbow_dot, -1.0, 1.0)
    left_elbow_theta = torch.acos(left_elbow_dot)
    left_elbow_q = quat_from_angle_axis(
        -torch.abs(left_elbow_theta),
        torch.tensor(np.array([[0.0, 1.0, 0.0]]), device=device, dtype=torch.float32),
    )

    left_elbow_local_dir = motion.skeleton_tree.local_translation[left_hand_id]
    left_elbow_local_dir = left_elbow_local_dir / torch.norm(left_elbow_local_dir)
    left_elbow_local_dir_tile = torch.tile(
        left_elbow_local_dir.unsqueeze(0), [left_elbow_rot.shape[0], 1]
    )
    left_elbow_local_dir0 = quat_rotate(left_elbow_rot, left_elbow_local_dir_tile)
    left_elbow_local_dir1 = quat_rotate(left_elbow_q, left_elbow_local_dir_tile)
    left_arm_dot = torch.sum(left_elbow_local_dir0 * left_elbow_local_dir1, dim=-1)
    left_arm_dot = torch.clamp(left_arm_dot, -1.0, 1.0)
    left_arm_theta = torch.acos(left_arm_dot)
    left_arm_theta = torch.where(
        left_elbow_local_dir0[..., 1] <= 0, left_arm_theta, -left_arm_theta
    )
    left_arm_q = quat_from_angle_axis(left_arm_theta, left_elbow_local_dir.unsqueeze(0))
    left_shoulder_rot = quat_mul(left_shoulder_rot, left_arm_q)

    # right leg
    right_thigh_pos = motion.global_translation[..., right_thigh_id, :]
    right_shin_pos = motion.global_translation[..., right_shin_id, :]
    right_foot_pos = motion.global_translation[..., right_foot_id, :]
    right_hip_rot = motion.local_rotation[..., right_thigh_id, :]
    right_knee_rot = motion.local_rotation[..., right_shin_id, :]

    right_leg_delta0 = right_thigh_pos - right_shin_pos
    right_leg_delta1 = right_foot_pos - right_shin_pos
    right_leg_delta0 = right_leg_delta0 / torch.norm(
        right_leg_delta0, dim=-1, keepdim=True
    )
    right_leg_delta1 = right_leg_delta1 / torch.norm(
        right_leg_delta1, dim=-1, keepdim=True
    )
    right_knee_dot = torch.sum(-right_leg_delta0 * right_leg_delta1, dim=-1)
    right_knee_dot = torch.clamp(right_knee_dot, -1.0, 1.0)
    right_knee_theta = torch.acos(right_knee_dot)
    right_knee_q = quat_from_angle_axis(
        torch.abs(right_knee_theta),
        torch.tensor(np.array([[0.0, 1.0, 0.0]]), device=device, dtype=torch.float32),
    )

    right_knee_local_dir = motion.skeleton_tree.local_translation[right_foot_id]
    right_knee_local_dir = right_knee_local_dir / torch.norm(right_knee_local_dir)
    right_knee_local_dir_tile = torch.tile(
        right_knee_local_dir.unsqueeze(0), [right_knee_rot.shape[0], 1]
    )
    right_knee_local_dir0 = quat_rotate(right_knee_rot, right_knee_local_dir_tile)
    right_knee_local_dir1 = quat_rotate(right_knee_q, right_knee_local_dir_tile)
    right_leg_dot = torch.sum(right_knee_local_dir0 * right_knee_local_dir1, dim=-1)
    right_leg_dot = torch.clamp(right_leg_dot, -1.0, 1.0)
    right_leg_theta = torch.acos(right_leg_dot)
    right_leg_theta = torch.where(
        right_knee_local_dir0[..., 1] >= 0, right_leg_theta, -right_leg_theta
    )
    right_leg_q = quat_from_angle_axis(
        right_leg_theta, right_knee_local_dir.unsqueeze(0)
    )
    right_hip_rot = quat_mul(right_hip_rot, right_leg_q)

    # left leg
    left_thigh_pos = motion.global_translation[..., left_thigh_id, :]
    left_shin_pos = motion.global_translation[..., left_shin_id, :]
    left_foot_pos = motion.global_translation[..., left_foot_id, :]
    left_hip_rot = motion.local_rotation[..., left_thigh_id, :]
    left_knee_rot = motion.local_rotation[..., left_shin_id, :]

    left_leg_delta0 = left_thigh_pos - left_shin_pos
    left_leg_delta1 = left_foot_pos - left_shin_pos
    left_leg_delta0 = left_leg_delta0 / torch.norm(
        left_leg_delta0, dim=-1, keepdim=True
    )
    left_leg_delta1 = left_leg_delta1 / torch.norm(
        left_leg_delta1, dim=-1, keepdim=True
    )
    left_knee_dot = torch.sum(-left_leg_delta0 * left_leg_delta1, dim=-1)
    left_knee_dot = torch.clamp(left_knee_dot, -1.0, 1.0)
    left_knee_theta = torch.acos(left_knee_dot)
    left_knee_q = quat_from_angle_axis(
        torch.abs(left_knee_theta),
        torch.tensor(np.array([[0.0, 1.0, 0.0]]), device=device, dtype=torch.float32),
    )

    left_knee_local_dir = motion.skeleton_tree.local_translation[left_foot_id]
    left_knee_local_dir = left_knee_local_dir / torch.norm(left_knee_local_dir)
    left_knee_local_dir_tile = torch.tile(
        left_knee_local_dir.unsqueeze(0), [left_knee_rot.shape[0], 1]
    )
    left_knee_local_dir0 = quat_rotate(left_knee_rot, left_knee_local_dir_tile)
    left_knee_local_dir1 = quat_rotate(left_knee_q, left_knee_local_dir_tile)
    left_leg_dot = torch.sum(left_knee_local_dir0 * left_knee_local_dir1, dim=-1)
    left_leg_dot = torch.clamp(left_leg_dot, -1.0, 1.0)
    left_leg_theta = torch.acos(left_leg_dot)
    left_leg_theta = torch.where(
        left_knee_local_dir0[..., 1] >= 0, left_leg_theta, -left_leg_theta
    )
    left_leg_q = quat_from_angle_axis(left_leg_theta, left_knee_local_dir.unsqueeze(0))
    left_hip_rot = quat_mul(left_hip_rot, left_leg_q)

    new_local_rotation = motion.local_rotation.clone()
    new_local_rotation[..., right_upper_arm_id, :] = right_shoulder_rot
    new_local_rotation[..., right_lower_arm_id, :] = right_elbow_q
    new_local_rotation[..., left_upper_arm_id, :] = left_shoulder_rot
    new_local_rotation[..., left_lower_arm_id, :] = left_elbow_q

    new_local_rotation[..., right_thigh_id, :] = right_hip_rot
    new_local_rotation[..., right_shin_id, :] = right_knee_q
    new_local_rotation[..., left_thigh_id, :] = left_hip_rot
    new_local_rotation[..., left_shin_id, :] = left_knee_q

    new_local_rotation[..., left_hand_id, :] = quat_identity([1])
    new_local_rotation[..., right_hand_id, :] = quat_identity([1])

    new_sk_state = SkeletonState.from_rotation_and_root_translation(
        motion.skeleton_tree, new_local_rotation, motion.root_translation, is_local=True
    )
    new_motion = SkeletonMotion.from_skeleton_state(new_sk_state, fps=motion.fps)

    return new_motion


def motion_from_fbx(fbx_file_path, root_joint, fps=60, visualize=True):
    # import fbx file - make sure to provide a valid joint name for root_joint
    motion = SkeletonMotion.from_fbx(
        fbx_file_path=fbx_file_path, root_joint=root_joint, fps=fps
    )
    # visualize motion
    if visualize:
        plot_skeleton_motion_interactive(motion)
    return motion


def motion_retargeting(retarget_cfg, source_motion, visualize=False):
    # load and visualize t-pose files
    source_tpose = SkeletonState.from_file(retarget_cfg["source_tpose"])
    if visualize:
        plot_skeleton_state(source_tpose, "source_tpose")

    target_tpose = SkeletonState.from_file(retarget_cfg["target_tpose"])
    if visualize:
        plot_skeleton_state(target_tpose, "target_tpose")

    # parse data from retarget config
    rotation_to_target_skeleton = torch.tensor(retarget_cfg["rotation"])

    # run retargeting
    target_motion = source_motion.retarget_to_by_tpose(
        joint_mapping=retarget_cfg["joint_mapping"],
        source_tpose=source_tpose,
        target_tpose=target_tpose,
        rotation_to_target_skeleton=rotation_to_target_skeleton,
        scale_to_target_skeleton=retarget_cfg["scale"],
    )

    # plot_skeleton_motion_interactive(target_motion)

    # keep frames between [trim_frame_beg, trim_frame_end - 1]
    frame_beg = retarget_cfg["trim_frame_beg"]
    frame_end = retarget_cfg["trim_frame_end"]
    if frame_beg == -1:
        frame_beg = 0

    if frame_end == -1:
        frame_end = target_motion.local_rotation.shape[0]

    local_rotation = target_motion.local_rotation
    root_translation = target_motion.root_translation
    local_rotation = local_rotation[frame_beg:frame_end, ...]
    root_translation = root_translation[frame_beg:frame_end, ...]

    new_sk_state = SkeletonState.from_rotation_and_root_translation(
        target_motion.skeleton_tree, local_rotation, root_translation, is_local=True
    )
    target_motion = SkeletonMotion.from_skeleton_state(
        new_sk_state, fps=target_motion.fps
    )

    # need to convert some joints from 3D to 1D (e.g. elbows and knees)
    # target_motion = _project_joints(target_motion)

    # move the root so that the feet are on the ground
    local_rotation = target_motion.local_rotation
    root_translation = target_motion.root_translation
    tar_global_pos = target_motion.global_translation
    min_h = torch.min(tar_global_pos[..., 2])
    root_translation[:, 2] += -min_h

    # adjust the height of the root to avoid ground penetration
    root_height_offset = retarget_cfg["root_height_offset"]
    root_translation[:, 2] += root_height_offset

    new_sk_state = SkeletonState.from_rotation_and_root_translation(
        target_motion.skeleton_tree, local_rotation, root_translation, is_local=True
    )
    target_motion = SkeletonMotion.from_skeleton_state(
        new_sk_state, fps=target_motion.fps
    )

    # save retargeted motion
    target_motion.to_file(retarget_cfg["target_motion_path"])

    if visualize:
        # visualize retargeted motion
        plot_skeleton_motion_interactive(target_motion)


def amp_npy_from_fbx(fbx_file, tpose_file, amp_tpose_file, verbose=True):
    """
    This scripts shows how to retarget a motion clip from the source skeleton to a target skeleton.
    Data required for retargeting are stored in a retarget config dictionary as a json file. This file contains:
      - source_motion: a SkeletonMotion npy format representation of a motion sequence. The motion clip should use the
                       same skeleton as the source T-Pose skeleton.
      - target_motion_path: path to save the retargeted motion to
      - source_tpose: a SkeletonState npy format representation of the source skeleton in it's T-Pose state
      - target_tpose: a SkeletonState npy format representation of the target skeleton in it's T-Pose state
                      (pose should match source T-Pose)
      - joint_mapping: mapping of joint names from source to target
      - rotation: root rotation offset from source to target skeleton (for transforming across different orientation
                  axes), represented as a quaternion in XYZW order.
      - scale: scale offset from source to target skeleton
    """
    target_motion_path = fbx_file[:-4] + ".npy"
    config = {
        "target_motion_path": target_motion_path,
        "source_tpose": tpose_file,
        "target_tpose": amp_tpose_file,
        "joint_mapping": {
            "Hips": "pelvis",
            "LeftUpLeg": "left_thigh",
            "LeftLeg": "left_shin",
            "LeftToeBase": "left_foot",
            "RightUpLeg": "right_thigh",
            "RightLeg": "right_shin",
            "RightToeBase": "right_foot",
            "Spine": "torso",
            "Head": "head",
            "LeftArm": "left_upper_arm",
            "LeftForeArm": "left_lower_arm",
            "LeftHand": "left_hand",
            "RightArm": "right_upper_arm",
            "RightForeArm": "right_lower_arm",
            "RightHand": "right_hand",
        },
        # "rotation": [0.707, 0, 0, 0.707], xyzw
        "rotation": [0.5, 0.5, 0.5, 0.5],
        "scale": 0.001,
        "root_height_offset": 0.0,
        "trim_frame_beg": 0,
        "trim_frame_end": -1,
    }

    motion = motion_from_fbx(fbx_file, root_joint="Hips", fps=60, visualize=verbose)
    config["target_motion_path"] = fbx_file.replace(".fbx", "_amp.npy")
    motion_retargeting(config, motion, visualize=verbose)


@click.command()
@click.option(
    "--is_parallel",
    default=False,
    help="Whether using parallel conversion.",
)
@click.option(
    "--verbose",
    default=False,
    help="Whether visualize the conversion.",
)
def main(is_parallel, verbose):
    data_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "../../../../data"
    )
    fbx_files = sorted(glob.glob(os.path.join(data_dir, '*.fbx')))
    tpose_file = os.path.join(data_dir, "tpose.npy")

    amp_humanoid_tpose_file = os.path.join(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data/amp_humanoid_tpose.npy"
    ))

    if is_parallel:
        pool = multiprocessing.Pool()
        pool.map(amp_npy_from_fbx, fbx_files)
    else:
        for fbx_file in fbx_files:
            amp_npy_from_fbx(fbx_file, tpose_file, amp_humanoid_tpose_file, verbose)


if __name__ == "__main__":
    main()