"""
Tracking the trajectory with multiple rigid bodies by Walker
============================================================

This example runs a Tai Chi demo bimanual trajectory by using Walker.
"""

import numpy as np

import rofunc as rf

traj_l = np.load('../data/LQT_LQR/taichi_1l.npy')
traj_r = np.load('../data/LQT_LQR/taichi_1r.npy')
traj_l[:, 0] -= 0.6
traj_r[:, 0] -= 0.6
# traj_l[:, 0] *= 0.5
# traj_r[:, 0] *= 0.5
# traj_l[:, 1] *= 0.5
# traj_r[:, 1] *= 0.5
rf.lqt.plot_3d_bi(traj_l, traj_r, ori=False)

args = rf.config.get_sim_config("Walker")
Walkersim = rf.sim.WalkerSim(args)
Walkersim.run_traj(traj=[traj_r, traj_l], update_freq=0.001)

