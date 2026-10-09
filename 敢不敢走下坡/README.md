# 敢不敢走下坡（模拟退火）

照视频号 trouble1422《年轻时，该不该多折腾？》的形式重做的一条 16:9 视频，58 秒。
结构、节奏、画面风格和三种走法的设定跟原片走；口播是我写的，小人重新画了一个（宽檐帽、提一盏灯，灯的亮度就是“敢走下坡”的温度），所有数字都来自 `sim.py` 自己跑的结果。

成片：`out/敢不敢走下坡_16比9.mp4`（1920×1080，30 fps，-14 LUFS）
封面：`out/敢不敢走下坡_封面_3比4.png`（1080×1440）

`out/` 不进仓库；成片和封面在 `output` 分支的 `敢不敢走下坡/`。

## 模拟是怎么做的（`sim.py`）

- 一条随机生成的山脉，最高点 1000 米。每个人只看得见脚下：每一步在附近随机挑一个点，上坡一定走，下坡 d 米按概率 exp(-d/T) 走。
- 求稳：T = 0，从不下坡。一直折腾：T 一辈子不变（50 米下坡 85% 会走）。先闯后收：T 从 18 岁开始按指数下降（时间常数 5 年），35 岁以后为 0。
- 18 岁到 60 岁，每年 120 步。60 岁时站在 970 米以上算登顶。
- 12 座山（第 1 座就是片中那座），每种走法每座山 4000 人：平均登顶率 求稳 3.9%、先闯后收 46.7%、一直折腾 12.1%；先闯后收在 10 座山上最高。
- 片中三个人的路线是从同一座山上挑出来讲故事用的（停在 696 米、沟深 121 米、19 岁跌到 58 米、20 岁最先登顶、不到 24 岁下山、25 岁登顶），统计数字不受这个挑选影响。

## 重新出片

```bash
cd 敢不敢走下坡
PY=python3                                   # 需要 numpy、edge-tts
npm install puppeteer-core                   # 渲染用本机的 Google Chrome
$PY sim.py                                   # -> data/sim.json（约 40 秒）
$PY tts.py                                   # 口播（edge-tts，云希）-> audio/line_*.wav、data/timeline.json
node render.mjs --events data/events.json    # 音效点
$PY mix.py                                   # 配乐 + 音效 + 口播 -> audio/final.wav
node render.mjs --out out/video.mp4 --workers 8
ffmpeg -y -i out/video.mp4 -i audio/final.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 256k -shortest -movflags +faststart "out/敢不敢走下坡_16比9.mp4"
node render.mjs --cover "out/敢不敢走下坡_封面_3比4.png" --w 1080 --h 1440
```

- 改口播：`script.json`（每句一行，`gap` 是句后停顿），改完从 `tts.py` 往下重跑。
- 改画面：`page/scene.js`，每帧都是时间 t 的纯函数；`node render.mjs --stills 3,12.5,40` 出单帧检查。
- 配乐全部在 `mix.py` 里合成（用的是 `extras/chonggu_intro/music.py`，在本分支根目录 的钢琴和铺底），没有采样。
- 配音换成自己录：把每句录成 `audio/line_XX.wav`（48 kHz 单声道），再改 `tts.py` 跳过合成那一步。
