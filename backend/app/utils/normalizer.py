import re

NORMALIZE = {
  r"和?牛.*(沙朗|肋條|牛小排|sirloin|short.?rib)": "牛肉",
  r"(青椒|青甜椒|ピーマン|green pepper)": "青椒",
  r"(胡蘿蔔|紅蘿蔔|carrot|にんじん)": "胡蘿蔔",
  r"(洋蔥|玉ねぎ|onion)": "洋蔥",
  r"(香菇|椎茸|しいたけ|shiitake)": "香菇",
  r"(蕎麥麵|蕎麦|soba|buckwheat noodles)": "蕎麥麵",
  r"(海苔|のり|nori)": "海苔",
  r"(蔥花|ねぎ|green onion|scallion)": "蔥",
  r"(山葵|わさび|wasabi)": "芥末(山葵)",
}

def normalize_name(name: str) -> str:
    for pat, canon in NORMALIZE.items():
        if re.search(pat, name, re.I):
            return canon
    return name