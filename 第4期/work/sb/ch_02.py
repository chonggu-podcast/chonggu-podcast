# ch 02 人家要的是能力 (顾东政). Threads: ch01's doors (学历 opens the first, 成绩 the second) -> intern badge
# -> the only red figure (department, then the years) -> what the job needs -> 问题 → 做出来 -> the road between
# -> the one-plank bridge (张飞 at the bridgehead, stamped 错) -> ch01's résumé again: the eye moves from 学历 to 能否胜任.
SERIF = {'fontFamily': 'var(--serif)', 'fontWeight': '900'}
BAR = {'color': 'light', 'css': {'borderRadius': '7px'}}

# A. first doubt: two doors in a row. 学历 opens the first (展示机会); the second (获得机会) opens only with 成绩.
scene('在我第一次认识到',
      K('第 一 段 怀 疑', y=180),
      Door(100, 300, w=320, h=480, inside='展示\n机会', isize=64, open_at='展示一个自己的机会'),
      Hd('学历', 260, 872, at='学历可以帮我', size=80, align='center'),
      Arr(448, 540, 140, at='但是获得这个机会'),
      Door(640, 300, w=320, h=480, inside='获得\n机会', isize=64, at='但是获得这个机会', open_at='拿出一些成绩'),
      Hd('成绩', 800, 872, at='拿出一些成绩', size=80, align='center'),
      Hd('？', 340, 872, at='我就开始怀疑', size=80, color='red'))

# B. second doubt: the intern badge fills in
# [朋友反馈 2026-10-05 更多真实照片] 工牌移到左边，右边是苏州的照片
scene('那么第二段怀疑',
      K('第 二 段 怀 疑', y=180),
      Box('', 60, 240, 440, 680),
      Box('', 220, 272, 120, 22, style='dark', delay=0.4, css={'borderRadius': '11px', 'padding': '0'}),
      Box('', 160, 336, 240, 260, delay=0.7),
      Ic('user', 190, 366, size=180, delay=1.0),
      Tag('实 习 生', 206, 624, at='实习工作', size=30),
      Hd('博世', 280, 700, at='博世实习', size=116, align='center'),
      Photo('suzhou', 540, 300, 480, 400, at='苏州博世公司', cap='苏 州', pos='35% 50%'))

# C1. the department: the team arrives, then its names, then the one red intern at the end of the row
scene('我是我们这个叫什么',
      K('部 门', y=180),
      *[Ic('user', 70 + i * 160, 250, size=140, delay=0.3 + i * 0.25) for i in range(5)],
      HL(60, 420, 960, delay=0.2, color='light'),
      Hd('Logistics Planner', 60, 470, at='LogisticsPlanner', size=76),
      P('Logistics Information Technology', 60, 580, at='LogisticsInformation', size=40),
      Ic('user', 870, 250, size=140, at='唯一的一名实习生', color='red'),
      Tag('实 习 生', 878, 432, at='唯一的一名实习生', size=28),
      News('bosch', X, 690, 860, at='我是我们这个+1.0', src='界面新闻 · 2023.01.13'))   # [朋友反馈 2026-10-05 新闻截图]

# C2. 2026 at Bosch: one red figure on the line — 唯一 (大一学生)
#     [朋友反馈 2026-10-05] 「他们是 23 年创立的……」那句删了：去掉 2023–2025 的刻度，只留 2026
scene('而且我也是2026年博世里面',
      HL(60, 520, 960, color='ink', thick=4, dur=1.0),
      {'kind': 'node', 'x': 960, 'y': 522, 'at': '2026年博世', 'red': True},
      P('2026', 960, 548, at='2026年博世', size=44, align='center', color='red', css=SERIF),
      Ic('user', 880, 340, size=160, at='2026年博世', color='red'),
      Big('唯一', 60, 250, at='唯一的一个大一', size=200, align='left'),
      P('大一学生', 486, 290, at='唯一的一个大一+0.3', size=52, css=SERIF),
      P('博世 · 2026', 486, 372, at='唯一的一个大一+0.6', size=30, color='gray'))

# D. not needed (struck) / needed (three drawn icons)
scene('那么这个工作其实我深入进去',
      K('并 不 需 要', y=180),
      P('高深的工作经验', 60, 230, at='高深的工作经验', size=50, color='gray'),
      {'kind': 'strike', 'x': 48, 'y': 266, 'w': 384, 'at': '高深的工作经验+0.7'},
      P('高深的大学经验', 560, 230, at='高深的大学经验', size=50, color='gray'),
      {'kind': 'strike', 'x': 548, 'y': 266, 'w': 384, 'at': '高深的大学经验+0.7'},
      HL(60, 350, 960, at='但是你需要', color='light'),
      K('需 要 的 是', y=400, at='但是你需要'),
      Ic('compass', 80, 470, size=200, at='极强的适应性'),
      Hd('适应性', 180, 700, at='极强的适应性', size=64, align='center'),
      Ic('book', 420, 470, size=200, at='保持学习的心态'),
      Hd('保持学习', 520, 700, at='保持学习的心态', size=64, align='center'),
      Ic('mountain', 760, 470, size=200, at='抗压能力'),
      Hd('抗压能力', 860, 700, at='抗压能力', size=64, align='center'))

# E. what the boss (the eye from ch01) wants: an empty slot from the start; a 问题 card -> along 需求 -> the slot
# fills red: 做出来
scene('那么领导想要的是什么呢',
      Ic('eye', 60, 168, size=110),
      K('领 导 想 要 的', x=196, y=210),
      Box('', 660, 360, 360, 300),
      Box('问题', 60, 360, 330, 300, at='眼前的问题', sub='眼前的', tsize=110, ssize=32, center=True),
      Arr(410, 510, 230, at='岗位他们的需求'),
      Lab('岗位的需求', 525, 444, at='岗位他们的需求', size=30, align='center', color='red'),
      K('最 重 要 的 是', x=660, y=312, at='最重要的是'),
      Box('做出来', 660, 360, 360, 300, at='做出来', style='dark', tsize=100, center=True,
          css={'background': 'var(--red)', 'borderColor': 'var(--red)'}))

# F. the road between what university teaches and doing well in the job
scene('当然这不代表大学学的东西',
      Ic('cap', 60, 200, size=170, at='大学学的东西'),
      Hd('大学学的东西', 260, 230, at='大学学的东西', size=76),
      P('不是没有价值', 260, 340, at='没有价值', size=38, color='gray'),
      {'kind': 'vline', 'x': 145, 'y': 400, 'h': 430, 'at': '中间还有一段', 'dur': 2.6, 'color': 'ink', 'thick': 4},
      Node(145, 400, at='中间还有一段'),
      Node(145, 830, at='中间还有一段+2.5', red=True),
      K('中 间 还 有 一 段', x=220, y=560, at='中间还有一段'),
      Hd('自己要走的路', 220, 610, at='自己要去走过的路', size=80, color='red'),
      Ic('target', 60, 860, size=170, at='在一个岗位上'),
      Hd('在岗位上做好', 260, 890, at='在一个岗位上', size=76))

# G. 985 · 211   [朋友反馈 2026-10-05] 「祖国的花朵」那句删了：去掉豆芽和引语
scene('比方说985',
      Photo('gaokao', 60, 200, 960, 470, cap='高 考 考 场', pos='50% 60%'),   # [朋友反馈 2026-10-05 真实照片]
      Big('985', 60, 760, at='985', size=220, align='left'),
      Big('211', 540, 760, at='211', size=220, align='left'),
      P('这种大学的学生', 60, 1010, at='这种大学的学生', size=40, color='gray'))

# H. 千军万马过独木桥: the crowd on one bank, a plank across the gap, one red dot crosses it and stands at the far
# bridgehead (张飞 at 长坂坡) and asks who dares pass; the crowd fades; 错 lands beside the question.
scene('那么大多数学生认为',
      K('大 多 数 学 生 认 为', y=180),
      HL(60, 640, 290, color='light', thick=10, delay=0.4),
      {'kind': 'vline', 'x': 345, 'y': 640, 'h': 130, 'delay': 0.8, 'thick': 10},
      HL(730, 640, 290, color='light', thick=10, delay=0.5),
      {'kind': 'vline', 'x': 735, 'y': 640, 'h': 130, 'delay': 0.9, 'thick': 10},
      Crowd(60, 470, 270, 300, n=40, cols=8, r=8, at='这么优秀的学生', pick_at='张飞'),
      P('千军万马', 195, 670, at='千军万马', size=34, align='center', color='gray'),
      Ruler(350, 600, w=380, ticks=1, minor=0, at='千军万马+0.4',
            labels=[{'pos': 0.5, 'text': '独木桥', 'at': '独木桥', 'size': 34}],
            dot={'from': 0.0, 'to': 1.0, 'at': '杀过独木桥', 'slide_at': '独木桥', 'dur': 1.2, 'ghost': False}),
      P('张飞', 730, 545, at='张飞+0.4', size=40, align='center', color='red', css=SERIF),
      News('gaokao', 210, 800, 660, at='千军万马', src='新华网 · 2026.06.03'))   # [朋友反馈 2026-10-05 新闻截图]

# [朋友反馈 2026-10-05 更多真实照片] 「长坂坡」拆成单独一场：月冈芳年的《张飞长坂桥》
scene('我一个人站在长坂坡',
      Photo('zhangfei', X, 240, 960, 520, cap='张 飞 · 长 坂 桥', pos='50% 35%', zoom=0.06),
      Bub('谁敢通过\n我的路？', 600, 860, at='谁敢通过我的路'),
      P('「没有人竞争过我」', X, 900, at='没有人竞争过我', size=44, css=SERIF))

scene('那么答案是什么呢',
      K('答 案 是 什 么 呢', y=200),
      Stamp('错', 540, 280, at='错', size=220, rot=-8, align='center'),
      Hd('人家要的是\n你有能力', X, 620, at='人家要的是你有能力', size=110, color='red'))

# J. ch01's résumé again. What you want: they see the 学历 line (a faint eye). What they want: a new line, 能否胜任,
# filled red, and the boss's eye (red) is on it. Then the cost on their side: a balance, 钱 ＋ 教你 ＝ 成本.
scene('那么你想要的是',
      Box('', 60, 240, 620, 560),
      Ic('user', 100, 266, size=110, delay=0.3),
      HL(240, 286, 300, delay=0.6, thick=22, **BAR),
      HL(240, 328, 200, delay=0.8, thick=14, **BAR),
      HL(100, 404, 540, delay=1.0, color='light'),
      HL(100, 528, 430, delay=1.2, thick=14, **BAR),
      HL(100, 566, 330, delay=1.3, thick=14, **BAR),
      HL(100, 728, 480, delay=1.5, thick=14, **BAR),
      HL(100, 764, 360, delay=1.6, thick=14, **BAR),
      P('你想要的', 830, 438, at='那么你想要的是', size=34, color='gray'),
      Marker('学历 · 国外大学', 104, 432, at='人家能看到我的学历', size=46),
      Ic('eye', 718, 411, size=100, at='人家能看到我的学历', css={'filter': 'opacity(.35)'}),
      P('人家想要的', 830, 624, at='人家想要的是', size=34, color='red'),
      Box('能否胜任这份工作', 92, 608, 556, 84, at='是否有能力', style='dark', tsize=50,
          css={'background': 'var(--red)', 'borderColor': 'var(--red)', 'padding': '0 14px'}),
      Ic('eye', 718, 600, size=100, at='是否有能力', color='red'),
      Ic('balance', 60, 846, size=130, at='毕竟我给你的是钱'),
      P('钱', 226, 862, at='是钱', size=56, css=SERIF),
      P('＋', 300, 862, at='我还要教你', size=56, color='gray'),
      P('教你', 376, 862, at='我还要教你', size=56, css=SERIF),
      P('＝', 520, 862, at='也需要成本', size=56, color='gray'),
      P('成本', 596, 856, at='也需要成本', size=64, color='red', css=SERIF))
