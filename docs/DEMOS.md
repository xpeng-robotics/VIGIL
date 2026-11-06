[Documentation](README.md) / Films and recordings

# Watch VIGIL

Start with the **68-second hardware walkthrough**: a short introduction to VIGIL,
then two complete robot-view replays with task explanations, decision steps and
playback progress. Faces are obscured throughout.

https://github.com/user-attachments/assets/9506aec4-7947-4272-87b9-9b700a432677

**[Download MP4](media/trailer.mp4?raw=true)** · 1:08 · 1080p

The video above plays directly on GitHub. The local player below also provides
chapter navigation. These are qualitative, controlled-intervention examples; the
closure labels are annotations in the source replay. See the [editing notes](TRAILER.md).

<details>
<summary>Research overview · 2:32</summary>

Eight task families, three complete simulator rollouts, and the distinction
between world completion and terminal reporting. All actions and failures in
the selected rollouts are retained; playback is not elapsed model time.

https://github.com/user-attachments/assets/1bd9f83d-87c9-466e-b1d6-88cdfeb50ef2

*2:32 · 1080p · English captions*

</details>

## Play with chapters

After cloning, run from the repository root:

```bash
python3 scripts/media/preview.py
```

A local player opens the walkthrough with playback controls, seeking and chapters.
Choose **Research film** for the longer overview or **Hardware** for full clips.
It needs only Python 3.10+ and a browser; no model or simulator starts.
The server supports byte-range requests so you can jump ahead before the whole
video downloads. Press Ctrl+C in the terminal to close it.

You can also open `docs/media/index.html` directly. A browser may download an MP4
link from GitHub instead of playing it inline; the downloaded file and local player
both support seeking. The older GIF is only an animated image and has no progress control.

## Hardware recordings

Open **Hardware** in the local player to watch these four clips. They are qualitative
examples, separate from the paper's quantitative AI2-THOR results. Faces are
obscured in all four recordings and their posters.

| Recording | View | Duration |
| --- | --- | ---: |
| [Object approach](media/demos/robot-1.mp4?raw=true) | External camera | 1:01 |
| [Room entry and fan search](media/demos/robot-2.mp4?raw=true) | External camera | 0:36 |
| [Person approach · Doubao-Seed-1.6](media/demos/robot-3.mp4?raw=true) | Observations and actions; controlled intervention | 0:16 |
| [Person approach · Gemini-3.1-Pro-preview](media/demos/robot-4.mp4?raw=true) | Observations and actions; controlled intervention | 0:24 |

The person-approach clips are step-sampled replays, not a controlled comparison
between models. The [research film evidence map](VIDEO.md) records sources, experimental
conditions and editing choices. The film describes the original paper dataset;
the [current release data](reference/DATA.md) includes later corrections.
