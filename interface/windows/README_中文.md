# Wireless Motion v3 使用步骤

这是独立的 Windows 界面版本，源码位于 interface/windows/，不替代 main 中的模型或训练程序。目前未接入真实模型；动作识别需交付适配器后验证，计数尚未实现。

## 打开

普通使用者：从 GitHub 的 interface-v0.3.1 预发布下载 ZIP，完整解压后双击其中 Wireless Motion 文件夹的 Start.bat 或 Wireless Motion.exe，无需 Python。保留 _internal。开发者：在本源码目录先运行 Install.bat（需要 Python 3.12），再运行 Start.bat；或者用 Build.bat 打包。

源代码入口仍是 app_v2.py；它复用 app.py 的基础控件和波形绘制，实际连接/录制由 controller.py 管理，分组由 workout.py 管理。普通使用只需 Start.bat。开发者重建时需先在 Build.bat 指定新的输出版本目录；脚本会阻止覆盖已有发布目录。

## 01 连接与准备

1. TX 通电，RX 用 USB 数据线连接电脑，关闭其他串口采集程序和 Arduino Serial Monitor。
2. 点 Connect device。只有一个端口时自动选中；多个端口时打开 Advanced settings 选择 RX。不会冒险自动探测所有设备。
3. 等待 RX firmware 显示 verified、TX packets 显示 receiving。USB 端口存在、固件验证和目标 TX 收包是分别检查的；软件不能直接判断 TX 电源、人体位置或识别准确度。
4. 填写 Participant 和 Placement，保持板子、线缆和人体实验位置固定。
5. 可选 Record 30-second baseline：静止站立，倒计时后自动保存独立 baseline 会话。至少 150 条样本并完成计时才标记 capture complete；这只是粗略采集门槛，不是校准成功或可识别性证明。中断/提前停止/样本不足会显示不完整。可到 Live workout 点击 End & save session 提前结束。
6. 点 Start workout 才开始正式保存。仅连接和预览不会创建录制目录，也不会推理；预览串口上下文只在内存限量保存。

## 02 实时运动

- 当前界面优先显示动作、RSSI 和录制时间。只有接入声明支持计数的模型时才显示次数卡片和 Confirmed repetitions 页签；分类器不会隐式启用计数。
- Activity predictions 显示模型输出的时间、动作和分数，最多保留最近 200 行；完整结果仍保存在 predictions.csv。Session records 可查看每场最近 1,000 条已保存预测。预测窗口不是动作重复次数，分数也不是已验证的准确率。
- Manual sets 保存人工划定的时间段；没有计数器时只显示组号和起止时间，不把整组强行归为某个动作。

- Current activity 显示模型预测的动作，不是用户手选标签。无模型时显示 — 和 signal only；不会伪造动作、置信度或次数。
- Repetitions in set 是当前组内模型确认的次数。仅有分类模型时次数卡片隐藏；只有声明支持计数并输出合法事件的适配器才能增加次数。
- Finish set 结束当前组。它不增加次数，也不修改动作类别；休息时模型事件不计入任何组。
- Start next set 开启下一组并重新预热模型时间窗口，旧组总数保留。新组次数从零或不可用开始。
- End & save session 自动结束当前组并保存，然后切换到 Session records。设备仍连接，回到 Connect & prepare 可继续开始下一场。
- 信号超过 2 秒没有新包时，清除旧的动作显示并提示中断。模型自身的长间隔门槛独立由 manifest 指定。
- Unknown 表示模型无法判断；Idle/other 必须来自真实模型输出。没有模型时软件不自行把静止判成 Idle。
- 等模型的最后一次动作确认显示后再点 Finish set，避免把尚未确认的动作截断；最终延迟规则需模型交付后实测。

## 03 训练记录

保存后自动显示会话总结。选择历史会话可查看参与者、摆放、时长、各动作总数及每组的动作/次数/时间范围。模型失败的会话会标记部分结果；没有模型的录制显示次数不可用，不会显示为真实零次。

每场 signal.csv、raw_serial.txt、predictions.csv、repetitions.csv、events.csv、metadata.json 保留；新增 sets.csv，repetitions.csv 新增 set_number。metadata 同样保存逐组汇总、计数可用状态和采集类型。观察、预测和人工分组边界分开保存。raw_serial 包含连接握手和部分预览上下文，因此其样本数可能多于从开始录制时起保存的 signal.csv。

默认输出在当前 app 项目根目录 sessions/，与 release_v3_1 分离，重新打包不会覆盖它。如果只把完整 Wireless Motion 程序文件夹单独发给别人，默认输出在 exe 旁 sessions/。高级设置可更改输出位置。

## 高级设置

包括串口、TX MAC、可信模型文件夹、卸载模型、输出目录。连接期间禁用；需要更换时先结束保存，再回准备页 Disconnect。模型路径不要求普通使用者填写，但最终交付时仍需开发者事先接入模型。

## 后续等模型再验证的部分

真实动作识别、在线计数精度、Idle/unknown 判定、最终确认延迟、模型依赖打包、30 秒基线如何应用校准、2/5 次示范适配、换人换摆放表现。当前没有实现“校准成功”、无数据的高位下拉识别或准确率保证。

给队友：MODEL_API.md 和 model_template/。分类器与计数器交付后，把 manifest 的 supports_counting 设为 true（仅在确实支持计数时），加入实际模型依赖、重建并用独立真实数据/两块实物板验证。
