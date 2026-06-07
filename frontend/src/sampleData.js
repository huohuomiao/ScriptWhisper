export const chapters = [
  {
    id: "chapter_1",
    title: "第一章 雨夜来信",
    summary: "林澈在旧影院门口与沈微重逢，收到十年前的电影票。",
    wordCount: 1680,
    status: "已分析",
  },
  {
    id: "chapter_2",
    title: "第二章 旧影院",
    summary: "两人进入影院，银幕开始播放林澈记忆中的巷子。",
    wordCount: 1420,
    status: "已分析",
  },
  {
    id: "chapter_3",
    title: "第三章 未完的对白",
    summary: "林澈意识到信写给当下的自己，并决定面对答案。",
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
  },
  characters: [
    {
      id: "lin_che",
      name: "林澈",
      role: "男主角",
      description: "带着旧信来到影院门口的人，长期回避十年前的选择。",
    },
    {
      id: "shen_wei",
      name: "沈微",
      role: "女主角",
      description: "等待多年并递出旧电影票的人，推动林澈面对答案。",
    },
  ],
  locations: [
    {
      id: "old_cinema",
      name: "旧影院门口",
      description: "雨停后的长街尽头，灯箱仍然亮着。",
    },
    {
      id: "projection_room",
      name: "放映室",
      description: "尘埃漂浮在光束里，旧放映机重新启动。",
    },
  ],
  scenes: [
    {
      id: "scene_1",
      title: "雨夜重逢",
      location_id: "old_cinema",
      characters: ["lin_che", "shen_wei"],
      summary: "林澈在旧影院门口见到沈微，并收到十年前的电影票。",
    },
    {
      id: "scene_2",
      title: "银幕亮起",
      location_id: "projection_room",
      characters: ["lin_che", "shen_wei"],
      summary: "放映机启动，银幕播放两人记忆中的巷子。",
    },
  ],
  script: [
    {
      scene_id: "scene_1",
      type: "action",
      content: "雨停后的长街泛着冷光。林澈握着没有署名的信，停在旧影院门口。",
    },
    {
      scene_id: "scene_1",
      type: "dialogue",
      character_id: "shen_wei",
      content: "如果今晚不进去，我们会再错过一次。",
    },
    {
      scene_id: "scene_1",
      type: "note",
      content: "镜头从湿漉漉的地面推向两人之间的电影票。",
    },
    {
      scene_id: "scene_2",
      type: "action",
      content: "放映室里传来机器启动的声音，银幕亮起。",
    },
    {
      scene_id: "scene_2",
      type: "dialogue",
      character_id: "lin_che",
      content: "原来那封信，从来不是写给过去的我。",
    },
    {
      scene_id: "scene_2",
      type: "transition",
      content: "银幕白光吞没画面。",
    },
  ],
};
