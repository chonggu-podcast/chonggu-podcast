# 第 4 期制作素材（顾东政 + 吴原同，一条成片）

- `work/make_plans.py`：剪辑表（录音里每一句的起止时间和校对后的字幕），生成 `plan_J.json`（顾东政 7 章 + 吴原同 7 章；脚本里的 A / B 是两人各自的段落）。
- `work/plan_to_edl.py` → `edl_J.json` → `work/assemble2.py`：按剪辑表剪音频。连着说的部分整段保留原始停顿和换气，只在删掉内容的地方剪接；字幕时间来自成片音频的整段识别。（旧的 `assemble.py` 逐句切开、句间插静音，已弃用。）
- `work/sb/ch_01.py … ch_14.py`：每章的竖版 3:4 分镜（97 个场景）；`work/sb_build.py` 合成 `storyboard_final.json`；`work/preview.sh` 渲染某几章的预览总览图。
- `work/build_ep.py` + `work/mix.py`：时间线和混音（-14 LUFS，约 -64 dBFS 底噪）。
- `render/engine.js`：渲染引擎。第 4 期新增：尺子、成绩榜（可模糊）、AI 聊天窗、曲线、积木、门、门票、印章、计数、点阵、荧光笔、划掉换词；方框先描边后填色；每个场景缓慢推近。
- `重估_片头_第4期_学历.json`：片头（顾东政三句版口播）的切句时间。
- `work/qa_asr.py`：成片音频整段重新识别，和剪辑表逐句对照。

录音原文件和整段逐字稿没有上传。

## 第二版和 4.1 / 4.2 两集（2026.10.05）

按朋友的反馈改了第二版（改动清单见 `output` 分支 `第4期/README.md` 末尾），又按说话人拆成 4.1 顾东政、4.2 吴原同两集，每集加 6 张新闻截图。成片在 `output` 分支：合集 `重估_第4期_学历_3比4_v3.mp4`，两集 `重估_4.1_学历_3比4_v2.mp4`、`重估_4.2_学历_3比4_v2.mp4`。

合集第二版的出片步骤（在 `第4期/` 里，`work/` 下需要放原始录音和 `transcript.json`，它们没有上传）：

```bash
cd 第4期/work
PY=<装了 numpy、scipy、pillow 的 python>
python3 make_plans.py && python3 plan_to_edl.py plan_J.json edl_J.json
ALIGN=map $PY assemble2.py edl_J.json edit_R          # 剪接点报告：edit_R/joins.json
python3 sb_build.py storyboard_final.json
EDIT_DIR=edit_R INTRO_BASE="重估_片头_第4期_学历" EP_JS=ep_v2.js $PY build_ep.py storyboard_final.json
EDIT_DIR=edit_R INTRO_BASE="重估_片头_第4期_学历" EP_JS=ep_v2.js $PY mix.py edit_R/final_audio.wav   # FX=0 不加音乐音效
cd ../render && EPJS=ep_v2.js node render.mjs --from 0 --to 1189.69 --workers 8 --out ../work/video_v3.mp4
```

- `ALIGN=map`：不重新跑 whisper，直接把 `transcript.json` 里 large-v3 的词时间按剪辑换算到成片上（和整段识别比，字的时间中位差 10 ms）。
- 分两集：同样的步骤，P=A 或 B，N=4.1 或 4.2：`python3 plan_to_edl.py plan_$P.json edl_${P}2.json`、`ALIGN=map $PY assemble2.py edl_${P}2.json edit_R$P`、`PART=$P python3 sb_build.py sb_${P}2.json`，build_ep / mix 用 `EDIT_DIR=edit_R$P INTRO_BASE="重估_片头_${N}_学历" EP_JS=ep_v3$P.js`，渲染 `EPJS=ep_v3$P.js`（4.1 到 698.09 秒，4.2 到 526.66 秒）。三份时间线 `render/ep_v2.js`、`ep_v3A.js`、`ep_v3B.js` 已经放进来，只改画面的话可以直接渲染。
- 封面：`node render/cover.mjs "$PWD/render/cover_41_v2.html" 重估_4.1_封面_竖版_v2.png`（4.2 同理）。
- 配乐和音效：`work/score_fx.py`（重点句列表 `KEY`、和弦、电平），由 `mix.py` 调用；每个点的时间在 `work/edit_R*/music_cues.json`。乐器来自 `extras/chonggu_intro/music.py`（片头生成器，也在这个目录里）。
- 照片：`render/photos/ep4_*.jpg`，来源和授权在 `render/photos/ep4_credits.json`；分镜里用 `Photo('key', x, y, w, h, at=…, cap=…)`（`work/sb_head.py`），画面上的署名自动生成。
- 新闻截图：`render/news/*.png`，由 `render/news_shot.mjs` 按手机宽度截取，只保留媒体名、标题和日期；出处和原文链接在 `render/news/sources.json`。
- 转场：`render/engine.js` 的 `drawScenes`；字幕逐字变色的开关是 `SUB_KARAOKE`（现在关着）。
- 渲染需要本机的 Google Chrome 和 `npm install puppeteer-core`（在 `render/` 里）。
