#! https://zhuanlan.zhihu.com/p/585106491

![](img/flyleaf.jpg)
# Rofunc：迈向高冗余人型机器人的多模态模仿学习



> 读博一周年纪念专栏

## 序

早就想开新专栏了，一直拖延到一周年零几个月。。。截至目前，旧的 RL in Robotics 专栏已累计98篇内容、5728个赞同。感谢各位对当年那个在迷雾中肆意探索的我给予的支持与鼓励，让我们缅怀一下这个即将完结的专栏：

[RL in Robotics](https://www.zhihu.com/column/c_1188392852261134336)

新专栏会更关注于机器人本身，尤其是更具挑战性的高冗余人型/类人型机器人的操作和行为，而不会像之前一样沉迷于某种听起来仿佛很厉害、但可能没大用的新技术。这可能也是我读博一年来的心得体会吧，总算是学会了从问题出发，而不是拿着锤子找钉子。这里就要感谢一下我导陈翡老师啦，以及一直为我提供硬核技术指导的 Sylvain Calinon 老师。

还有一点与之前不同的是，这次的专栏其实也是我们正在推进的开源机器人模仿学习库 `Rofunc` 的中文教程。在科研的过程中分心搞工具包开发的初衷也很简单。在深度学习领域，我们有 `torch`；在图学习领域，我们有 `DGL`；在强化学习领域，我们有 `RLlib`。为什么机器人领域就不能拥有这种易用的、普适的，且能够一览机器人任务从数据到部署全流程的工具包呢？

技术的本质就应该是解蔽，而不是打着科研招牌的故弄玄虚。只有机器人门槛放低，才会吸引更多志同道合的朋友投入到机器人社区的建设中，才会最终迎来那姗姗来迟的机器人革命。那么，先上 `Rofunc` 的 `Github Repository` 吧！

[Rofunc Github](https://github.com/Skylark0924/Rofunc)

欢迎 **Star**，欢迎 **Issue**，欢迎 **Contributor**，欢迎一切志同道合的小伙伴！！！

![](img/power.jpg)




## 概览

机器人的模仿学习/示教学习并不是一个很新的话题，甚至读博这一年我也接触到了欧洲和美国两种不同的思想流派。像 Billard 教授和 Calinon 老师这样的欧洲研究者坚守在拖动示教以及由此衍生基于概率和流形的示教学习方法（可以参考一下 [李淼老师的回答](https://www.zhihu.com/question/265564182/answer/309412387)）。而美国呢，貌似更喜欢基于视频示教直接使用DL、RL等 NN-based 方法。这两种思路是各有优势，也是各有缺点的，优劣是需要根据具体任务来评判的。我们想做的，就是在 `Rofunc` 中同时引入这两种思路，为 peer researchers 提供一个模仿学习的 baseline 甚至是 benchmark package。

除了 learning 模块外，我们还有更大的野心：**提供从多模态数据采集与处理、示教学习到机器人规划与控制、以及具有多种类人机器人仿真器的全流程示教学习 pipeline。** 对于高冗余度的类人型机器人来说，从人类演示中学习 (learning from human demonstration) 是获取新的、复杂的技能最自然且便捷的解决方案。我们提供了多视角视觉（ZED camera）、人类运动学（Xsens MTw Awinda）、物体运动学（Optitrack）以及人体生物力学（Delsys sEMG）的多传感器、多模态采集与处理方案，提供了基于优化的机器人规划与控制方法，也同样提供了基于 Isaac Gym 的多种机器人（Franka, CURI, Ubetch Walker, Diablo等）仿真器。

![](../img/../../img/pipeline.png)


## 目录

> 持续更新中