#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Single source of truth: slide list, on-screen copy, bilingual speech.
Deck and speech document are both generated from this file."""

TITLE_EN = "Wukang Road: Then and Now"
TITLE_ZH = "武康路：十五年前与现在"

# n, minutes, on-screen cues, English speech, Chinese translation
SLIDES = [
    dict(
        n=1, t="0:00",
        cue=["Wukang Road", "2010 → 2026"],
        en=("Good morning, everyone. My name is Zhang San. Today I want to take you to one street in "
            "Shanghai — Wukang Road. It is only 1.17 kilometres long, but in the last fifteen years it has "
            "changed more than most streets change in a hundred."),
        zh=("各位老师、同学，早上好。我叫张三。今天我想带大家去看上海的一条马路——武康路。"
            "它全长只有 1.17 公里，但过去十五年里，它的变化比很多马路一百年的变化还要大。"),
    ),
    dict(
        n=2, t="0:25",
        cue=["1.17 km", "51 protected buildings", "30 famous homes"],
        en=("Wukang Road lies in Xuhui District. It was built in 1907, and for most of its life it was just a "
            "quiet lane of plane trees and old villas. Along this short road there are fifty-one protected "
            "historic buildings and about thirty former homes of famous writers and politicians. "
            "That is the raw material. The real question is: what happened to it?"),
        zh=("武康路在徐汇区。它建于 1907 年，在漫长的时间里，它只是一条安静的、种满法国梧桐和老洋房的马路。"
            "就在这一小段路上，有 51 处保护建筑，还有大约 30 处名人旧居。这是它的底子。"
            "真正的问题是：它后来发生了什么？"),
    ),
    dict(
        n=3, t="0:55",
        cue=["Quiet", "Local", "Wired"],
        en=("Let us start with \"then\". Around 2010, this was a residential street. Neighbours did not lock "
            "their doors, and they shared food with each other. There was a market, a grocery, a barber's shop. "
            "If you wanted a photograph of the famous Wukang Mansion, you had to wait for the traffic light — "
            "and even then, a web of overhead cables cut the building into pieces."),
        zh=("先看「过去」。2010 年前后，这里是一条居民生活的马路。邻居不锁门，彼此送吃的；"
            "街上有菜场、杂货铺、理发店。如果你想拍那张著名的武康大楼，只能等红灯的间隙——"
            "而且就算拍到了，头顶一张「蜘蛛网」般的电线也会把大楼切得七零八落。"),
    ),
    dict(
        n=4, t="1:25",
        cue=["25,000 a day", "100,000 at peak", "400,000 in 3 days"],
        en=("Now look at it. On an ordinary day, twenty to thirty thousand people walk through this block. "
            "On a holiday, the number can reach a hundred thousand. In the Dragon Boat holiday of 2021, more "
            "than four hundred thousand visitors came here in three days. This street has become the city's "
            "most famous \"City Walk\"."),
        zh=("再看「现在」。平常日子，这个街区每天有两三万人走过；节假日峰值能到十万人。"
            "2021 年端午假期，三天里涌进来四十多万游客。这条马路成了全城最有名的「City Walk」。"),
    ),
    dict(
        n=5, t="1:55",
        cue=["Tourism", "Buildings", "Business", "Transport", "Image"],
        en=("So what actually changed? Five things. Tourism: from local residents to thousands of visitors. "
            "Buildings: from old and forgotten to restored and protected. Business: from corner shops to cafés "
            "and boutiques. Transport: from local traffic to walking and cycling. And the image: from \"a street "
            "in Shanghai\" to \"a landmark of Shanghai\"."),
        zh=("那到底变了什么？五件事。旅游：从本地居民变成成千上万的游客。建筑：从年久失修、无人知晓，"
            "变成修复保护。业态：从街角小店变成咖啡与买手店。交通：从居民通行变成步行与骑行。"
            "街区形象：从「上海的一条马路」变成「上海的地标」。"),
    ),
    dict(
        n=6, t="2:20",
        cue=["2018 → 2019", "0 overhead cables"],
        en=("The first change is the skyline. In 2018 the city began to put the overhead cables underground — "
            "the first project of its kind in central Shanghai. On the twenty-fifth of January 2019, the last "
            "two cables were taken down. For the first time in decades, you could photograph this building "
            "against the sky."),
        zh=("第一个变化是天际线。2018 年，上海开始把架空线埋到地下——这是中心城区的第一条。"
            "2019 年 1 月 25 日，最后两根架空线被拆除。几十年来第一次，你可以把这座大楼完整地拍在天空里。"),
    ),
    dict(
        n=7, t="2:45",
        cue=["2009", "2019", "51"],
        en=("The second change is the building itself. Nothing was demolished. In 2009 the block had its first "
            "restoration. In 2019 came a much bigger one — four months of what the designer called \"building "
            "archaeology\". His rule was simple: make it look as if it had never been repaired."),
        zh=("第二个变化是建筑本身。没有一栋被拆掉。2009 年做了第一次修缮；2019 年是一次更大的修缮——"
            "四个月，设计者把它叫作「建筑考古」。他的原则只有一句：修完之后，要像从来没修过一样。"),
    ),
    dict(
        n=8, t="3:10",
        cue=["80% cafés", "144 firms", "¥100m tax"],
        en=("The third change is business. Twenty years ago you came here to buy vegetables; now you come for "
            "coffee. Of the twenty-five most popular places to eat on this street, about eighty per cent are "
            "cafés, western restaurants or ice-cream shops, and most of the brands are new Chinese brands. "
            "It pays: by 2023 the businesses here paid more than one hundred million yuan in tax."),
        zh=("第三个变化是业态。二十年前你来这儿买菜，现在你来喝咖啡。这条街上人气最高的 25 家餐饮里，"
            "约 80% 是咖啡、西餐或冰淇淋店，而且大部分是新的中国品牌。它也确实赚钱：到 2023 年，"
            "这个街区的企业税收超过一亿元。"),
    ),
    dict(
        n=9, t="3:35",
        cue=["+3.6 m", "+500 m²", "109 objects"],
        en=("The fourth change is the street space. When tourists started standing in the road to take photos, "
            "the city did not ban them. It widened the pavement by three point six metres, added five hundred "
            "square metres of standing space, and removed a hundred and nine obstacles — poles, boxes, "
            "air-conditioners. The traffic lights now even carry the street names."),
        zh=("第四个变化是街道空间。当游客开始站到马路中间拍照，政府没有禁止他们，而是把人行道向外拓了 3.6 米，"
            "增加了五百多平方米的停留空间，还清掉 109 处「城市家具」——立杆、箱体、空调外机。"
            "现在连红绿灯上都写着路名。"),
    ),
    dict(
        n=10, t="4:00",
        cue=["Policy", "Renewal", "Culture", "Social media"],
        en=("Why did all this happen? Four reasons. Policy: Shanghai wrote a protection plan for this road in "
            "2008 and restored it step by step. Renewal: cables, pavements, greenery, street furniture. "
            "Culture: people became interested in history, and the city opened its old buildings to the public. "
            "And social media: one photograph on a phone can make a street famous overnight."),
        zh=("为什么会发生这些？四个原因。政策：2008 年上海为这条马路专门编制了保护规划，一步一步修。"
            "更新：架空线、道板、绿化、街道家具。文化：人们开始对历史感兴趣，城市也把老建筑对公众打开。"
            "还有社交媒体：手机里一张照片，就能让一条马路一夜成名。"),
    ),
    dict(
        n=11, t="4:30",
        cue=["Residents", "Shop owners", "Students", "Tourists", "City"],
        en=("Who gained? Almost everyone. Residents got safer streets and better surroundings. Shop owners got "
            "more customers. Students like us got a living textbook of history and architecture. Tourists got "
            "old Shanghai in one place. And the city got a brand — and a tax base."),
        zh=("谁受益了？几乎所有人。居民得到了更安全的街道和更好的环境；店主得到了更多客人；"
            "像我们这样的学生得到了一本会走路的历史与建筑教科书；游客在一个地方就看到了老上海；"
            "而城市得到了一个品牌，还有一份税收。"),
    ),
    dict(
        n=12, t="4:55",
        cue=["1,000 photos a day", "An 80-year-old moved out", "Rent ×3"],
        en=("But fame has a bill, and someone has to pay it. In 2021 a resident hung a pink bow on her balcony. "
            "Within days, more than a thousand people a day stood under it and called her name. She was eighty "
            "and lived alone. In the end her family took her away, and the bow came down. At the same time, "
            "rents on this street rose from fifteen yuan per square metre to fifty or sixty, and the cheap "
            "shops that made the street liveable moved out."),
        zh=("但名气是有账单的，总得有人付。2021 年，一位居民在自家阳台挂了一个粉色蝴蝶结。"
            "几天之内，每天有一千多人站在楼下喊她。她八十岁，独居。最后家人把她接走了，蝴蝶结也摘了下来。"
            "与此同时，这条街的租金从每平方米 15 元涨到 50–60 元，那些让街区有生活气的平价小店被挤了出去。"),
    ),
    dict(
        n=13, t="5:25",
        cue=["Coexist", "Long-term value", "Stories"],
        en=("So what should we learn? Three things. History and development are not enemies — this street proves "
            "they can grow together. Protecting heritage creates long-term value, not just a pretty photograph. "
            "And a community's greatest treasure is not its newest building, but the stories it keeps."),
        zh=("那我们应该学到什么？三点。历史与发展不是敌人——这条街证明它们可以一起生长；"
            "保护文化遗产创造的是长期价值，而不只是一张好看的照片；"
            "一个社区最珍贵的财富，不是它最新的楼，而是它留下来的故事。"),
    ),
    dict(
        n=14, t="5:50",
        cue=["Thank you"],
        en="Respect the past, and the future will have something to stand on. Thank you for listening.",
        zh=("尊重过去，未来才有立足之地。谢谢大家的聆听。"),
    ),
]
