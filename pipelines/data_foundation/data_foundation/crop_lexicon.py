# -*- coding: utf-8 -*-
"""Data Foundation · 作物/价格 token 分类词表（唯一真源）
被 build_dimensions.py 与 build_standardized.py 共同引用，避免多处重复规则。
classify(token) -> (standard_name, category, field_role, is_crop, flag)
  field_role ∈ crop / grade / specification / package / processing_state /
               seedling / ornamental / processed_food / livestock_part /
               agric_input / basket / non_crop / unknown
"""
from __future__ import annotations
from pathlib import Path
import re

# (canonical, category, [aliases/varieties...])
CROP_MASTER = [
    ("黄瓜", "vegetable", ["青瓜", "水黄瓜", "刺黄瓜", "旱黄瓜"]),
    ("西红柿", "vegetable", ["番茄", "硬粉西红柿", "大红西红柿", "粉西红柿", "樱桃番茄", "小柿子", "圣女果", "普罗旺斯"]),
    ("尖椒", "vegetable", ["青尖椒", "黄皮椒", "薄皮椒", "螺丝椒"]),
    ("青椒", "vegetable", ["圆椒", "灯笼椒", "甜椒", "青椒王", "太空椒", "麻椒"]),
    ("辣椒", "vegetable", ["红辣椒", "干辣椒", "朝天椒", "线椒", "小米椒", "杭椒"]),
    ("芹菜", "vegetable", ["西芹", "本芹", "香芹"]),
    ("土豆", "vegetable", ["马铃薯", "荷兰十五", "脱毒马铃薯"]),
    ("茄子", "vegetable", ["紫茄子", "长茄子", "圆茄子", "紫长茄", "黑紫长茄", "圆茄"]),
    ("甘蓝", "vegetable", ["圆白菜", "卷心菜", "绿甘蓝", "京丰一号", "甘兰"]),
    ("紫甘蓝", "vegetable", []),
    ("韭菜", "vegetable", []),
    ("芸豆", "vegetable", ["菜豆", "架豆王", "豆角", "九粒白芸豆", "四季豆", "扁豆", "白条豆角", "长豇豆", "豇豆", "毛豆", "毛豆荚"]),
    ("大白菜", "vegetable", ["白菜", "黄心白菜", "娃娃菜"]),
    ("大葱", "vegetable", ["小葱", "葱", "香葱"]),
    ("菜花", "vegetable", ["花椰菜", "西兰花", "青花菜", "白花菜"]),
    ("胡萝卜", "vegetable", ["红萝卜"]),
    ("白萝卜", "vegetable", ["萝卜", "红皮萝卜", "青萝卜", "水萝卜"]),
    ("油菜", "vegetable", ["小白菜", "上海青", "青菜"]),
    ("菠菜", "vegetable", []),
    ("茼蒿", "vegetable", []),
    ("生菜", "vegetable", ["油麦菜"]),
    ("角瓜", "vegetable", ["西葫芦", "茭瓜"]),
    ("苦苣", "vegetable", ["苦菊"]),
    ("香菜", "vegetable", ["芫荽"]),
    ("洋葱", "vegetable", ["圆葱", "元葱", "黄洋葱", "紫洋葱"]),
    ("蒜苔", "vegetable", ["蒜薹"]),
    ("大蒜", "vegetable", ["蒜", "红皮蒜", "白皮蒜", "蒜头", "蒜米"]),
    ("生姜", "vegetable", ["姜", "老姜", "鲜姜"]),
    ("南瓜", "vegetable", ["贝贝南瓜"]),
    ("冬瓜", "vegetable", []), ("丝瓜", "vegetable", []), ("苦瓜", "vegetable", []),
    ("荷兰豆", "vegetable", []), ("豌豆", "vegetable", []),
    ("莴笋", "vegetable", ["莴苣"]), ("山药", "vegetable", []), ("藕", "vegetable", ["莲藕"]),
    ("香菇", "vegetable", ["平菇", "鲜平菇", "金针菇", "杏鲍菇", "木耳", "食用菌", "蘑菇", "滑子蘑", "榛蘑", "羊肚菌"]),
    ("芥菜", "vegetable", []), ("茴香", "vegetable", []), ("空心菜", "vegetable", []),
    ("木耳菜", "vegetable", []), ("秋葵", "vegetable", []), ("菜心", "vegetable", []), ("苋菜", "vegetable", []),
    ("甜菜", "vegetable", []), ("芋头", "vegetable", []),
    ("红薯", "vegetable", ["地瓜", "甘薯", "白薯", "红薯干", "蜜薯"]),
    ("玉米", "grain", ["干玉米", "籽粒玉米", "鲜食玉米", "甜玉米", "糯玉米", "粘玉米", "玉米棒", "玉米面", "玉米糁"]),
    ("水稻", "grain", ["粳稻", "稻谷", "大米", "东北大米", "佃米", "盘锦大米"]),
    ("小麦", "grain", ["面粉", "特一粉", "特二粉", "富强粉", "标准粉", "精粉", "雪花粉"]),
    ("大豆", "grain", ["黄豆", "东北大豆"]),
    ("高粱", "grain", ["高粱米", "红高粱"]),
    ("谷子", "grain", ["小米", "杂粮", "黄金小米"]),
    ("花生", "grain", ["花生米", "四粒红"]),
    ("薯类", "grain", []), ("绿豆", "grain", ["东北绿豆"]), ("红豆", "grain", []),
    ("苹果", "fruit", ["金红123", "寒富", "红富士", "嘎啦", "黄元帅", "国光"]),
    ("梨", "fruit", ["南果梨", "白梨", "花盖梨", "苹果梨"]),
    ("香蕉", "fruit", []), ("柑橘", "fruit", ["橙子", "橘子", "蜜桔", "沃柑", "砂糖橘"]),
    ("葡萄", "fruit", ["京亚葡萄", "巨峰葡萄", "阳光玫瑰"]),
    ("桃", "fruit", ["油桃", "毛桃", "水蜜桃", "久保桃", "黄桃"]),
    ("樱桃", "fruit", ["佳红", "大樱桃", "美早"]),
    ("草莓", "fruit", ["红颜草莓", "甜查理草莓", "蒙特瑞草莓", "艳丽草莓", "九九草莓"]),
    ("蓝莓", "fruit", ["北陆蓝莓"]), ("猕猴桃", "fruit", []), ("软枣猕猴桃", "fruit", []),
    ("西瓜", "fruit", ["麒麟西瓜", "甜王西瓜"]), ("甜瓜", "fruit", ["香瓜", "东方蜜甜瓜", "阎良甜瓜"]),
    ("枣", "fruit", ["红枣", "大枣", "冬枣"]), ("杏", "fruit", ["山杏"]), ("李子", "fruit", ["红叶李"]),
    ("柿子", "fruit", ["冻柿子"]), ("石榴", "fruit", []), ("板栗", "fruit", ["栗子", "油栗", "锥栗", "丹东板栗"]),
    ("核桃", "fruit", ["核桃仁", "纸皮核桃"]), ("榛子", "fruit", []), ("山楂", "fruit", ["山楂干"]),
    ("海棠果", "fruit", ["锦绣海棠果"]),
    ("猪肉", "livestock", ["去骨后腿肉", "五花肉", "白条猪", "鲜猪肉", "五花猪肉", "后腿肉", "猪后腿", "净猪肉", "猪副产品", "猪蹄", "猪排骨"]),
    ("牛肉", "livestock", ["鲜牛肉", "和牛", "牛后腿", "牛腩"]),
    ("羊肉", "livestock", ["鲜羊肉", "羔羊", "绵羊", "奶羊", "山羊", "绒山羊", "羯羊", "下架羊", "羊排"]),
    ("鸡肉", "livestock", ["白条鸡", "白条鸡上等", "肉鸡", "下架鸡", "土鸡", "笨鸡", "鸡腿", "鸡翅"]),
    ("鸡蛋", "livestock", ["混码鸡蛋", "大码鸡蛋", "中码鸡蛋", "小码鸡蛋", "乌鸡蛋", "笨鸡蛋", "红皮鸡蛋"]),
    ("牛奶", "livestock", ["生鲜乳", "鲜奶", "纯牛奶"]),
    ("生猪", "livestock", ["三元猪", "仔猪", "什猪", "育肥猪"]),
    ("肉牛", "livestock", []), ("肉羊", "livestock", []),
    ("鸭肉", "livestock", ["下架鸭", "白条鸭"]), ("鸭蛋", "livestock", ["咸鸭蛋"]),
    ("鹅肉", "livestock", ["笨肉鹅", "大鹅"]),
    ("鲤鱼", "aquatic", []), ("草鱼", "aquatic", []), ("鲫鱼", "aquatic", []), ("带鱼", "aquatic", []),
    ("对虾", "aquatic", ["青虾", "白虾"]), ("鲈鱼", "aquatic", []), ("胖头鱼", "aquatic", ["花鲢"]),
    ("马口鱼", "aquatic", []), ("海鱼", "aquatic", ["鲅鱼", "黄花鱼"]),
    ("蚕茧", "other_agri", ["蚕", "蚕蛹"]),
    ("蜂蜜", "other_agri", ["洋槐蜜", "椴树蜜"]),
    ("蔬菜", "basket", ["新鲜蔬菜"]), ("水果", "basket", ["速冻蔬果", "冻草莓", "冻蓝莓", "冻梨"]),
    ("粮油", "basket", ["豆油", "色拉油", "散油", "猪油", "芝麻油", "食用油"]),
    ("肉蛋奶", "basket", ["肉禽蛋", "肉蛋"]), ("水产", "basket", []),
    ("16种蔬菜均价", "basket", ["16种蔬菜平均价"]), ("15种蔬菜均价", "basket", []),
    ("18种蔬菜均价", "basket", []), ("19种蔬菜均价", "basket", []), ("12种蔬菜均价", "basket", []),
]

# 追补：长尾别名 / 水产 / 药材 / 噪声
EXTRA_CANON = [
    ("鹅蛋", "livestock", ["鲜鹅蛋", "土鹅蛋", "咸鹅蛋", "笨鹅蛋"]),
    ("羊奶", "livestock", []),
    ("龙眼", "fruit", ["桂圆", "桂圆干"]),
    ("树莓", "fruit", ["覆盆子"]),
    ("姑娘果", "fruit", ["菇娘"]),
    ("淡水鱼", "aquatic", ["鲢鱼", "白鲢鱼", "白条鱼", "麦穗鱼", "镜鲤", "裸鲤", "泥鳅", "花泥鳅",
                          "银鱼", "翘嘴鲌鱼", "马哈鱼", "草鱼", "鲫鱼", "鲤鱼", "胖头鱼", "黄颡鱼", "罗非鱼"]),
    ("海鱼", "aquatic", ["小黄鱼", "鳕鱼", "带鱼", "鲅鱼", "黄花鱼", "偏口鱼", "鲳鱼"]),
    ("虾蟹贝", "aquatic", ["北极虾", "青虾", "白虾", "生蚝", "牡蛎", "乳山牡蛎", "扇贝", "花甲", "小龙虾"]),
    ("中药材", "non_crop", ["黄精", "鸡头黄精", "北沙参", "沙参", "淫羊藿", "藁本", "赤灵芝", "灵芝",
                            "穿心莲", "石斛", "枸杞", "五味子", "刺五加", "威灵仙", "金线莲"]),
]

# 追加别名（合并进既有 canonical）
EXTRA_ALIASES = {
    "黄瓜": ["黃瓜", "黄爪"],
    "胡萝卜": ["胡萝", "胡萝心"],
    "甘蓝": ["包菜", "大头菜", "疙瘩白"],
    "油菜": ["鸡毛菜", "小油菜"],
    "芸豆": ["矮生刀豆", "刀豆", "油豆角", "紫花油豆"],
    "香菇": ["红菇", "椴木菇", "滑子菇", "大球盖菇", "猴头菇", "干猴头菇", "双孢菇", "口蘑"],
    "水稻": ["粳米", "香米", "稻花香", "长粒香", "珍珠米"],
    "花生": ["花育25", "白沙"],
    "大蒜": ["独头蒜"],
    "辣椒": ["红泡椒", "泡椒", "牛角椒"],
    "茄子": ["黑长茄", "青茄", "白茄", "紫黑长茄"],
    "软枣猕猴桃": ["软枣"],
    "蚕茧": ["柞蚕"],
    "蜂蜜": ["荆条蜜", "百花蜜", "荔枝蜜", "槐花蜜", "枣花蜜", "椴树蜜"],
    "鸡肉": ["鸡胸肉", "鸡腿肉", "鸡", "麻鸡"],
    "牛肉": ["牛", "黄牛", "杂交牛", "牛犊", "精瘦肉", "去骨瘦肉"],
    "鹅肉": ["杂交鹅", "鹅"],
    "鸭肉": ["麻鸭", "鸭"],
    "鸡蛋": ["初生蛋", "绿壳蛋", "咸蛋", "粉壳蛋"],
    "猪肉": ["猪心", "猪精瘦肉", "猪肝", "猪肠", "猪舌", "猪脑", "猪杂", "猪黄喉"],
    "羊肉": ["羊杂", "羊头"],
    "蔬菜": ["山野菜", "刺老芽", "紫苏"],
    "海棠果": ["海棠"],
    "草莓": ["黔莓1号"],
    "柑橘": ["丑橘", "耙耙柑", "柑桔"],
    "菜花": ["花菜"],
    "红薯": ["烟薯"],
    "芥菜": ["雪里红"],
    "桃": ["白桃", "蟠桃", "艳红桃", "红桃", "燕川红桃"],
    "枣": ["金丝小枣"],
    "淡水鱼": ["雄鱼", "公鱼", "青鱼", "重唇鱼", "鱿鱼", "中华花鳅", "花鳅"],
    "海鱼": ["鲑鱼", "比目鱼"],
    "虾蟹贝": ["飞蟹", "虾姑", "梭子蟹"],
    "中药材": ["苍术", "北苍术", "细辛", "厚朴树", "马勃"],
}
for _canon, _cat, _al in EXTRA_CANON:
    CROP_MASTER.append((_canon, _cat, _al))
for _canon, _al in EXTRA_ALIASES.items():
    for _i, (_c, _cat, _a) in enumerate(CROP_MASTER):
        if _c == _canon:
            CROP_MASTER[_i] = (_c, _cat, list(_a) + _al)
            break

CANON: dict[str, tuple[str, str]] = {}
for canon, cat, al in CROP_MASTER:
    CANON[canon] = (canon, cat)
    for a in al:
        CANON[a] = (canon, cat)

GRADE_PAT = re.compile(r"^(一等|二等|三等|四等|特级|特一|特二|特一粉|特二粉|标一|标二|标准|一级|二级|三级|上等|中等|下等|统货|市场价|优|特等|一等品|二级品|一等果|二等果|三等果|上等果|A|B|C|A级|B级|C级|1级|2级|3级|上|中|下)$")
SEED_PAT = re.compile(r"(苗$|种子|树苗|种苗|幼苗|嫁接苗|组培苗|种球)")
ORN_PAT = re.compile(r"(枫|松|柏|柳|槐|榆|杉|栎|冬青|黄杨|女贞|迎春|紫荆|红瑞木|连翘|玉簪|锦带|红叶李|桧|丁香|白桦|花楸|云杉|蒙古栎|文冠果|玫瑰|月季|兰花|剑兰|绿萝|常春藤|木槿|蔷薇|杜鹃|萱草|小檗|槭|银杏|铃兰|海棠树|果树)")
FEED_PAT = re.compile(r"(饲料|化肥|尿素|复合肥|农药|农膜|柴油|水溶肥|元素水溶|秸秆|有机肥|鸡粪|栽培基质|基质|稻草|干草)")
PROC_PAT = re.compile(r"(桶装|袋装|散装|箱装|装箱|礼盒|盒装|瓶装|罐装)")
PROCFOOD_PAT = re.compile(r"(调味酱|蒜蓉酱|花草茶|蒲公英茶|^糖$|^食糖$|^食盐$|速冻|冻品|酸菜|泡菜|包子|罐头|调料)")
PARTS_PAT = re.compile(r"(蹄|排骨|内脏|下水|骨头|爪|翅|肝|肠|肚|血|尾|副产品)")
SPEC_PAT = re.compile(r"^(新鲜完整|新鲜|完整|去骨|后腿|前腿|五花|净|整|切|段|丝|片|块|带皮|去皮|鲜|冻|冷藏|冷冻|速冻)$|(?:\d+\s*(?:公斤|斤|克|ml|毫升|升|L|枚|头|只|千克))")
NOISE_PAT = re.compile(r"(居委会|水量|燃料|枚|套袋|叶片|合计|平均|元|其他|其它|无)$")


def classify(raw: str):
    """返回 (standard_name, category, field_role, is_crop, flag)"""
    r = (raw or "").strip()
    if not r:
        return ("", "", "unknown", False, "empty")
    if r in CANON:
        canon, cat = CANON[r]
        return (canon, cat, "crop", True, "exact")
    # 子串：canonical/alias 出现在 token 内
    for k, (canon, cat) in CANON.items():
        if len(k) >= 2 and k in r:
            return (canon, cat, "crop", True, "substr")
    if GRADE_PAT.match(r):
        return ("", "grade", "grade", False, "grade")
    if SEED_PAT.search(r):
        return ("", "non_crop", "seedling", False, "seedling")
    if ORN_PAT.search(r):
        return ("", "non_crop", "ornamental", False, "ornamental")
    if FEED_PAT.search(r):
        return ("", "non_crop", "agric_input", False, "agric_input")
    if PARTS_PAT.search(r):
        return ("", "non_crop", "livestock_part", False, "livestock_part")
    if PROC_PAT.search(r):
        return ("", "package", "package", False, "package")
    if PROCFOOD_PAT.search(r):
        return ("", "non_crop", "processed_food", False, "processed_food")
    if SPEC_PAT.search(r):
        return ("", "spec", "specification", False, "specification")
    if NOISE_PAT.search(r):
        return ("", "non_crop", "non_crop", False, "noise")
    return ("", "unknown", "unknown", False, "unmapped")


if __name__ == "__main__":
    import sys, csv
    from collections import Counter
    path = sys.argv[1] if len(sys.argv) > 1 else str(Path(next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())) / "data/metadata/inventory/token_inventory.csv")
    d = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    res = Counter(); unmapped = []
    for row in d:
        t = row.get("token") or row.get("raw_name") or ""
        n = int(row.get("count") or row.get("n_obs") or 0)
        canon, cat, role, iscrop, flag = classify(t)
        res[flag] += n
        if flag == "unmapped":
            unmapped.append((n, t))
    print("=== 按行数 ===")
    for k, v in res.most_common():
        print(f"  {k}: {v}")
    unmapped.sort(reverse=True)
    print(f"\n=== unmapped distinct {len(unmapped)} / rows {sum(n for n,_ in unmapped)} ===")
    for n, t in unmapped[:200]:
        print(n, t)
