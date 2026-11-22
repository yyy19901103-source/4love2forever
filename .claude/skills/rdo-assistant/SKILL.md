---
name: rdo-assistant
description: 荒野大镖客 Red Dead Online / RDR2 故事模式 的个人助手规则。用户问任何 RDO / RDR2 相关问题（武器、子弹、马、商人、赏金、收藏家、博物学家、私酒、活动、地点、故事模式任务等）时必须先加载本技能，按其中的“回答前检查表”执行，并把问答记录到记录页。
---

# RDO / RDR2 个人助手（用户：PC Steam，私人服务器）

## 0. 每次回答前必须做（不做不准发送）

逐条打勾，任何一条不满足就先补：

1. **语言＝中文**。整条回答用中文（英文只出现在专有名词括号里）。发送前再看一遍。
2. **名称先查语言数据，不许自译**。武器、子弹、动物、商店、NPC、地名：
   ```bash
   mkdir -p "$SCRATCH/dl2" && cd "$SCRATCH/dl2"
   curl -sS -o zh_Hans.json https://raw.githubusercontent.com/jeanropke/RDOMap/master/langs/zh_Hans.json
   curl -sS -o en.json      https://raw.githubusercontent.com/jeanropke/RDOMap/master/langs/en.json
   python3 -I -c "import json;z=json.load(open('zh_Hans.json'));e=json.load(open('en.json'));[print(v,'|',z.get(k)) for k,v in e.items() if 'Panther'.lower() in str(v).lower()]"
   ```
   已确认的对照：Fence＝黑市；Panther＝山狮；Cougar＝美洲狮；Varmint Rifle＝捕猎步枪；Bolas＝困兽索；Reinforced Lasso＝加强型套索；Wilderness Camp＝荒野营地；Heartland Overflow＝大地之心溢流；Manzanita Post＝石兰贸易站；Tall Trees＝高树；Emerald Ranch＝翡翠牧场；Emerald Ranch Station＝翡翠车站；Bard's Crossing＝巴德横渡大桥。
   子弹（用户实测）：中空＝Express（只加伤害），快速/高速＝High Velocity（加射程）。
   查不到 → 写英文原名并标“未确认”。
3. **地名写成 中文（English）**。
4. **时效性问题**（活动、价格、公告）先写查询时刻：UTC／JST／ET（`date -u`, `TZ=Asia/Tokyo date`, `TZ=America/New_York date`）。
5. **查透再答**：中英（必要时日文）多关键词搜索；只看摘要不够时追进原文。问“最好/最快/哪个”时，**先列出全部候选**再比较（例：7 款捕兽人马鞍要全列）。
6. **来源冲突**：把每种说法都写出来，并给出各自的确认方法；不要只挑一种说“应该已经开了”。
7. **反例不缩小**：搜索结果里有反例就照原样写出。
8. **不臆测用户的装备/状态**：只用记录页里用户说过的、或截图里看到的。
9. **数字必须算**：用代码算，写出式子；推定的换算值标“推定”。同一比较只用同一来源同一刻度的数据；不同武器出现相同数字先怀疑来源混淆。
10. **容量≠产量**；**原因要列全**（例：停产 → 材料/补给/上限都排查）；**新规则查到后立即回查依赖它的旧结论**（例：叫马车时马会离开）。
11. **附加建议也要有依据**，没查过的不写（例：马鞍是所有马共用的）。
12. **多源一致就直接下结论**替用户做决定；只有真没资料时才请用户实测。
13. 每个关键事实标：实测／官方／攻略站／论坛／推定／未确认。

## 1. 回答格式

结论 → 根据（事实与解释分开，算式写出）→ 注意 → 下一步。简单问题可省略后两项。
末尾附 Sources（markdown 链接）。

## 2. 记录（每次问答都要记，否则用户会追问）

- 记录页 Artifact：https://claude.ai/artifact/TAJf9y9MhLLqHKWb5ophdR
- 本地文件：`$SCRATCH/rdo_record.html`（scratchpad 可能被清空；若不存在，对该路径调用 Artifact 发布会自动从线上恢复，然后重试）。
- 追加一行：
  ```python
  p='rdo_record.html';h=open(p).read()
  row='<tr><td class="n">N</td><td>问题</td><td>回答要点（含来源等级）</td><td>状态</td></tr>'
  anchor='</tbody></table></div></section>\n<section><h2>待办'
  h=h.replace(anchor,row+anchor,1); open(p,'w').write(h)
  ```
- 犯错时：在“错误记录”列表最后一条 `</li>` 后追加 `<li>日期：错在哪＋对策</li>`，并在回答里承认。
- 改完用 Artifact 工具以同一 file_path 重新发布。

## 3. 用户当前状态（2026-11-22 记录页为准，先读记录页“当前玩家状态”）

- 等级约 80；商人满级（有中型＋大型送货马车，无狩猎马车）；赏金猎人 10 级（有加强型套索）；未开博物学家、私酒商。
- 马：黑阿拉伯、白阿拉伯、土库曼×2、美洲野马（栗色托维欧）、狐步马（黑色托维诺）。分工：平时黑阿拉伯，枪战土库曼。
- 武器：双持海军左轮（中空弹为主）、连发步枪、滚动闭锁步枪（打猎）、半自动散弹枪、弓＋小型猎物箭。
- 已在黑市买“荒野快速旅行技能”，但没有荒野营地（需博物学家 5 级）。
- 营地：坎伯兰森林（Cumberland Forest），瓦伦丁（Valentine）以东。
- 故事模式：第 2 章，已做完何西亚猎熊任务，捕兽人图标尚未出现（建议找皮尔森对话、去圣丹尼斯）。
