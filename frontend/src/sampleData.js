export const chapters = [
  {
    id: "chapter_1",
    title: "第一章 雨夜来信",
    summary: "林澈在旧影院门口与沈微重逢，收到十年前的电影票。",
    content:
      "雨停后的长街泛着冷光。林澈握着那封没有署名的信，终于在旧影院门口看见了等候多时的沈微。\n\n她没有开口，只把一张泛黄的电影票递给他。票根上的日期停在十年前，像一枚还没有落下的钉子。\n\n林澈想转身离开，沈微却说，如果今晚不进去，他们会再错过一次。",
    wordCount: 1680,
    status: "已分析",
  },
  {
    id: "chapter_2",
    title: "第二章 旧影院",
    summary: "两人进入影院，银幕开始播放林澈记忆中的巷子。",
    content:
      "影院大门被风推开，尘埃在光束里缓慢漂浮。放映室里传来机器启动的声音，银幕却没有播放任何电影。\n\n林澈看见十年前的巷子，看见自己没有说出口的那句话。沈微站在他身旁，像早就知道画面会出现。\n\n白光吞没银幕时，林澈终于明白，那封信不是写给过去的自己。",
    wordCount: 1420,
    status: "已分析",
  },
  {
    id: "chapter_3",
    title: "第三章 未完的对白",
    summary: "林澈意识到信写给当下的自己，并决定面对答案。",
    content:
      "林澈把信纸重新展开。纸上的字迹被潮气晕开，却仍能看清最后一行：别再替我沉默。\n\n沈微没有催他，只等他把那张电影票放回掌心。旧影院的灯一盏盏亮起，像迟到多年的回答。\n\n他转向沈微，说这一次他会把话讲完。",
    wordCount: 1260,
    status: "待复核",
  },
];

export const scriptYaml = {
  project: {
    title: "雨夜来信",
    version: "1.0",
    genre: "悬疑短剧",
    logline: "旧影院重逢的一夜，让两个人重新面对十年前错过的答案。",
    source: "sample_novel_3chapters.txt",
    source_language: "zh",
    bible: {
      story_type: "情感悬疑短剧",
      main_conflict: "林澈想继续逃避十年前的选择，沈微逼他重新进入旧影院面对真相。",
      central_mystery: "那封没有署名的信到底写给过去的林澈，还是写给此刻仍在逃避的他。",
      adaptation_advice: "保留旧影院、电影票和白光门作为贯穿意象，把回忆信息分散到每个场景的动作和对白中。",
    },
  },
  characters: [
    {
      id: "lin_che",
      name: "林澈",
      role: "男主角",
      description: "带着旧信来到影院门口的人，长期回避十年前的选择。",
      personality: "克制、敏感、习惯回避冲突",
      motivation: "弄清旧信来源，并确认自己是否还有弥补的机会",
      speech_style: "短句多，常用反问和停顿隐藏真实情绪",
      first_chapter: "第一章 雨夜来信",
    },
    {
      id: "shen_wei",
      name: "沈微",
      role: "女主角",
      description: "等待多年并递出旧电影票的人，推动林澈面对答案。",
      personality: "冷静、坚定、带有压抑的锋芒",
      motivation: "让林澈停止逃避，重新走进两人共同的旧伤口",
      speech_style: "语气平静但指向明确，常用条件句制造压力",
      first_chapter: "第一章 雨夜来信",
    },
  ],
  locations: [
    {
      id: "old_cinema",
      name: "旧影院门口",
      description: "雨停后的长街尽头，灯箱仍然亮着。",
      atmosphere: "潮湿、冷光、怀旧又压抑",
      plot_use: "重逢入口，触发电影票和旧信的核心线索",
    },
    {
      id: "projection_room",
      name: "放映室",
      description: "尘埃漂浮在光束里，旧放映机重新启动。",
      atmosphere: "封闭、昏暗、机械声带来不安节奏",
      plot_use: "让记忆影像实体化，推动林澈面对十年前的选择",
    },
  ],
  scenes: [
    {
      id: "scene_1",
      title: "雨夜重逢",
      location_id: "old_cinema",
      characters: ["lin_che", "shen_wei"],
      summary: "林澈在旧影院门口见到沈微，并收到十年前的电影票。",
      source_ref: {
        chapter_id: "chapter_1",
        chapter_index: 1,
        chapter_title: "第一章 雨夜来信",
        excerpt: "雨停后的长街泛着冷光。林澈握着那封没有署名的信，终于在旧影院门口看见了等候多时的沈微。",
      },
      beats: {
        goal: "林澈想确认旧信与电影票的来源。",
        conflict: "沈微逼他进入旧影院，林澈仍想回避十年前的错过。",
        turn: "沈微拿出十年前的电影票，改变林澈对重逢的理解。",
        outcome: "林澈被迫留下，故事进入旧影院内部。",
      },
    },
    {
      id: "scene_2",
      title: "银幕亮起",
      location_id: "projection_room",
      characters: ["lin_che", "shen_wei"],
      summary: "放映机启动，银幕播放两人记忆中的巷子。",
      source_ref: {
        chapter_id: "chapter_2",
        chapter_index: 2,
        chapter_title: "第二章 旧影院",
        excerpt: "影院大门被风推开，尘埃在光束里缓慢漂浮。放映室里传来机器启动的声音。",
      },
      beats: {
        goal: "两人进入放映室，寻找银幕出现异常影像的原因。",
        conflict: "银幕播放的不是电影，而是林澈反复逃避的记忆。",
        turn: "沈微说出如果今晚不进去，两人会再错过一次。",
        outcome: "林澈意识到旧信指向的是此刻的选择。",
      },
    },
  ],
  script: [
    {
      id: "line_1",
      scene_id: "scene_1",
      type: "action",
      content: "雨停后的长街泛着冷光。林澈握着没有署名的信，停在旧影院门口。",
    },
    {
      id: "line_2",
      scene_id: "scene_1",
      type: "dialogue",
      character_id: "shen_wei",
      content: "如果今晚不进去，我们会再错过一次。",
    },
    {
      id: "line_3",
      scene_id: "scene_1",
      type: "note",
      content: "镜头从湿漉漉的地面推向两人之间的电影票。",
    },
    {
      id: "line_4",
      scene_id: "scene_2",
      type: "action",
      content: "放映室里传来机器启动的声音，银幕亮起。",
    },
    {
      id: "line_5",
      scene_id: "scene_2",
      type: "dialogue",
      character_id: "lin_che",
      content: "原来那封信，从来不是写给过去的我。",
    },
    {
      id: "line_6",
      scene_id: "scene_2",
      type: "transition",
      content: "银幕白光吞没画面。",
    },
  ],
};
