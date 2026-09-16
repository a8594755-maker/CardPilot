# 固定大规模训练脚本

只写脚本；本次没有启动训练或新 Slumbot 测试。

默认**随机初始化**，不是把已有模型的历史手数清零。单 seed、全网络
PPO、原生 v6 200bb、GN、普通 critic_v1；25% 当前模型自我对弈，75%
历史 latest-8 对手（池未建立时全部自我对弈）。不使用 Slumbot 标签、
专用规则、固定教师或 KL 拉回。所有动作 sampled T=1。训练不使用 replay。
12 workers，每个8环境，GPU批量推理；每轮16384个有训练样本的手，2个
PPO epochs，初始lr=1e-4，gamma=lambda=1。第一阶段使用训练器按实际手数的
衰减日程；20M阶段保留10M终点的优化器学习率，不因目标变大把学习率跳回。
此选择是固定长程实验，不是已经证明最优的算法。

在仓库根目录执行（默认 plan 不启动任何任务）：

```powershell
python scripts/alpha_holdem/long_run_10m.py plan
python scripts/alpha_holdem/long_run_10m.py train10m
python scripts/alpha_holdem/long_run_10m.py test10m
python scripts/alpha_holdem/long_run_10m.py train20m
```

每条命令只执行一个阶段，结束后停下供工程检查，不自动搜索或切换算法。
10M之前不做 Slumbot 小测。test10m 固定冻结10M模型、40个全新2500手会话，
共100000手；完成全部会话后全量模型回放与会话独立性检查，再报告原始
bb/100、普通95%CI与session-t95%CI。两种下界均大于0才标记该统计条件满足；
这不自动宣称总体Goal完成或通用最优。服务器随机流独立性只能做经验检查。
本脚本的单seed实验也不能替代后续多seed和异质对手的泛化评估。

train20m 要求先完成test10m并核对同一个10Mcheckpoint，保留Adam、历史对手、
主进程RNG和计数，只把累计实际手数目标提高到20M。它不是额外训练20M。

手数以 completed environment hands 为准，包含无可训练决策的终局；到达
阈值后在更新边界退出，会略超10M/20M，结果记录实际值，不截掉或伪造手数。
transition hands单独记录，不把它与环境手数混淆。

每20次更新保存latest，每200次更新保留归档，并永久保留阶段终点；不是
每几千手保存一份完整大checkpoint。启动时复制并绑定运行代码和包版本。
所有阶段自动创建、更新及finish实验记录。发生技术异常停止后续阶段，
保留日志与checkpoint，不替换失败会话、不自动重新启动训练。

**恢复限制：** managed deal namespace避免重用旧牌序；不承诺多worker
中断时的在途轨迹逐位恢复。意外中断必须先审查checkpoint、worker尾部和
日志，再编写明确恢复命令。不要删除stage目录来绕过保护。正常10M到20M
续训才由上述命令直接支持。

脚本已做参数表面、阶段目标和保护测试；**尚未进行真实GPU运行验收**。
正式开跑前应确认GPU/磁盘、驱动、没有竞争训练任务，并做一次隔离的运行
验收。不要把静态测试通过当成1000万手训练已经完成。
