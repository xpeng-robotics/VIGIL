<div align="center">

<p><strong>VIGIL · NeurIPS 2026 · Poster</strong></p>
<h1>Done, But Not Sure</h1>
<p>Disentangling World Completion from Self-Termination in Embodied Agents</p>

<p>
  <a href="https://arxiv.org/abs/2605.08747">论文</a> &nbsp;·&nbsp;
  <a href="https://xpeng-robotics.github.io/vigil/">项目主页</a> &nbsp;·&nbsp;
  <a href="README.md">文档</a> &nbsp;·&nbsp;
  <a href="../README.md">English</a>
</p>

</div>

https://github.com/user-attachments/assets/1bd9f83d-87c9-466e-b1d6-88cdfeb50ef2

<p align="center"><sub>2 分 32 秒 · Benchmark 介绍</sub></p>

VIGIL 是评测具身智能体任务完成与自主终止能力的基准。它分别记录环境中的任务状态和智能体的最终报告，
从而识别过早宣称成功、完成任务后却未报告等行为。

基准包含 AI2-THOR 中的 1,000 个评测回合，覆盖八类任务；智能体通过第一视角 RGB 图像导航并与物体交互。
仓库提供任务数据、评测工具和本地轨迹回放工作台。

[查看真机演示 →](DEMOS.md)

## 先体验录制好的示例

准备 **Python 3.10+**，克隆仓库并启动工作台：

```bash
git clone https://github.com/xpeng-robotics/VIGIL.git
cd VIGIL
bash start.sh
```

选择 **Explore a recorded run**，选中一个 episode，再打开 **Replay**，
逐步查看相机图像、模型动作和结果。这里使用仓库自带的录像，无需安装依赖、配置模型密钥或启动模拟器。
macOS 也可以双击 `start.command`。

继续配置前，在终端按 **Ctrl+C** 关闭工作台。

## 运行自己的评测

需要一个支持图像输入的模型 API，以及能够运行 AI2-THOR 的 Linux 或 macOS 主机。
模型推理可以部署在另一台机器上，也可以使用托管服务。以下命令均在克隆后的仓库根目录执行。

### 1. 安装评测依赖

下面的 `python3` 需要是 Python 3.10+；如有需要，替换为 `python3.10` 或其他受支持的解释器。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[thor]"
```

仓库已包含任务数据和场景文件。首次启动模拟器时，可能会下载 Unity 运行资源到 `~/.ai2thor`。

无桌面的 Linux 主机在准备好 Vulkan 渲染环境后，选择 cloud 渲染：

```bash
export VIGIL_THOR_PLATFORM=cloud
```

驱动要求、Apple Silicon 与 Rosetta 配置见[安装指南](guides/INSTALLATION.md#rendering-platforms)。

### 2. 连接模型

对于兼容 OpenAI 接口的视觉模型服务，创建配置：

```bash
vigil init --backend openai-compatible \
  --model YOUR_VISION_MODEL \
  --base-url http://127.0.0.1:8000/v1
```

将模型名称和地址替换为已运行的模型服务。接口必须同时支持图像和文本输入。
如果服务需要认证，在同一个终端中设置密钥：

```bash
export VIGIL_API_KEY="YOUR_API_KEY"
```

配置保存在 `vigil.json`。如果文件已存在，可以直接编辑，或运行 `vigil ui`，
在 **Run an evaluation** 中填写设置并点击 **Save configuration**。
命令行和工作台使用同一份配置。原生 Gemini、Anthropic 接口及本地模型部署见[模型配置指南](guides/MODEL_EVAL.md)。

### 3. 跑通一个任务

先检查配置和渲染环境，再执行一个完整任务：

```bash
vigil doctor
vigil doctor --check-simulator
vigil smoke --out-dir outputs/first-run
```

`doctor` 检查本地配置；`--check-simulator` 启动 Unity 并检查 RGB 图像；
`smoke` 在一个任务上运行完整的模型调用、动作执行和评分流程。
它会调用你的模型 API，并将结果保存到 `outputs/first-run`。

也可以运行 `vigil ui`，在 **Run an evaluation** 中依次选择 **Check setup** 和
**Run 1 episode**。通过工作台发起的每次评测，会在 `outputs/` 下创建带时间戳的新目录。

### 4. 查看结果

对于上面的命令行运行：

```bash
vigil verify-run outputs/first-run --require-frames
vigil report outputs/first-run
vigil ui --results-dir outputs/first-run
```

在工作台中可以回放观察与动作，并查看最终报告。每次运行将 RGB 图像保存在 `frames/`，
逐步记录保存在 `traces/`，单任务评分保存在 `scores/`，汇总结果保存在 `aggregate_score.json`。

| 结果 | 衡量内容 |
| --- | --- |
| 世界完成率 W | episode 结束时，任务要求的环境状态是否成立。 |
| 基准成功率 B | 环境状态成立，并且提交了符合要求的正确终止报告。 |

`verify-run` 检查保存的证据、单任务评分与汇总结果是否一致。
任务失败仍可以是有效评测结果；API 或模拟器出错则需要先解决，才能得到最终基准指标。

## 批量评测与续跑

单任务跑通后，先尝试一个小批次：

```bash
vigil run --max-episodes 10 --workers 1 --out-dir outputs/my-model-10
```

去掉任务数量限制，即可运行完整的 1,000 个 episode：

```bash
vigil run --workers 1 --out-dir outputs/my-model-full
```

这两个命令均保留原始任务步数预算，并保存回放图像。
确认渲染资源和 API 配额后，可以增加 `--workers`；并发数与渲染进程上限的关系见
[评测指南](guides/EVALUATION.md#understand-the-concurrency-controls)。

在另一个已激活相同环境的终端中查看进度：

```bash
vigil progress outputs/my-model-full
```

如果运行中断，保持模型、代码、数据和设置一致，执行：

```bash
vigil run --workers 1 --out-dir outputs/my-model-full --resume-existing
```

已经完成且通过核验的 episode 会被复用。更换模型或修改设置时，应使用新的输出目录。
完成后，将上一节的 `verify-run`、`report` 和 `ui --results-dir` 路径替换为 `outputs/my-model-full`，
即可核验和查看完整结果。

上述命令使用当前基准版本，其中包含论文之后的任务与输入协议修正，默认配置并非精确复现论文表格的预设。
[基准版本与论文对照](reference/PAPER_ALIGNMENT.md)说明了这些差异，以及核验历史结果需要的原始档案。

## 引用

<details>
<summary>BibTeX</summary>

```bibtex
@inproceedings{chen2026done,
  title     = {Done, But Not Sure: Disentangling World Completion from Self-Termination in Embodied Agents},
  author    = {Chen, Ying and Fang, Lihuang and Jiang, Rui and Wang, Mingxu and Gu, Zhifeng and Yi, Lei and Chen, Jie},
  booktitle = {Advances in Neural Information Processing Systems},
  year      = {2026},
  url       = {https://arxiv.org/abs/2605.08747}
}
```

</details>

## 许可证

原创代码、任务定义和标注采用 [Apache-2.0](../LICENSE)。
模拟器、场景和模型资源保留上游条款，见[第三方声明](../licenses/THIRD_PARTY_NOTICES.md)。
