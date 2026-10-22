#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并同学交回来的语料。

为什么需要它：15 个人各交一个 .jsonl，格式一定会乱 ——
空行、多轮写错、role 写错、一个文件里塞了别的东西、复制粘贴带出了中文引号……
手工检查 15 个文件不现实，这个脚本把脏东西挡住，只把干净的合进去。

用法：
    python3 合并语料.py 收到的/                      # 看看情况，先不写文件
    python3 合并语料.py 收到的/ -o 合并.jsonl         # 确认没问题再真合并
    python3 合并语料.py 收到的/ --min-len 10         # 太短的答案判为不合格（默认 2）

输入：目录下所有 .jsonl（每行一个 {"messages":[...]}）
输出：
    1) 合并后的 .jsonl（只有 --write 时才写）
    2) 一份体检报告：每个文件交了几条、哪几行有问题、为什么
"""

import argparse
import glob
import json
import os
import sys
from collections import Counter

ROLES = {"user", "assistant", "system"}


def check_sample(obj, min_len):
    """返回 (是否合格, 原因, 轮数, 字数)。"""
    if not isinstance(obj, dict):
        return False, "不是一个 JSON 对象", 0, 0
    msgs = obj.get("messages")
    if not isinstance(msgs, list) or not msgs:
        return False, "没有 messages 数组（或者是空的）", 0, 0

    chars = 0
    for i, m in enumerate(msgs):
        if not isinstance(m, dict):
            return False, "第 %d 轮不是一个对象" % (i + 1), 0, 0
        role, content = m.get("role"), m.get("content")
        if role not in ROLES:
            return False, "第 %d 轮的 role 是 %r（只能是 user/assistant/system）" % (i + 1, role), 0, 0
        if not isinstance(content, str):
            return False, "第 %d 轮的 content 不是字符串" % (i + 1), 0, 0
        # 门槛只管 AI 的回答 —— 用户的话本来就短（"什么意思" 4 个字很正常）
        if role != "user" and len(content.strip()) < min_len:
            return False, "第 %d 轮（%s）太短：%d 字，要求 ≥%d" % (
                i + 1, role, len(content.strip()), min_len), 0, 0
        chars += len(content)

    if not any(m["role"] == "user" for m in msgs):
        return False, "没有 user 轮", 0, 0
    if not any(m["role"] == "assistant" for m in msgs):
        return False, "没有 assistant 轮", 0, 0
    if msgs[-1].get("role") != "assistant":
        return False, "最后一句不是 assistant（模型学不到怎么回答）", 0, 0

    return True, "", len(msgs), chars


def main():
    ap = argparse.ArgumentParser(description="合并多人交回来的语料")
    ap.add_argument("目录", help="放 .jsonl 的目录")
    ap.add_argument("-o", "--output", default="语料-合并.jsonl", help="合并后写到哪")
    ap.add_argument("--min-len", type=int, default=2,
                    help="AI 每句回答最少几个字（默认 2；想和《说明》里\"至少 10 字\"一致就用 10。用户的话不受此限）")
    ap.add_argument("--write", action="store_true", help="真的写文件（不加只做体检）")
    ap.add_argument("--allow-dup", action="store_true", help="允许完全相同的样本重复出现")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.目录, "*.jsonl")))
    if not files:
        print("这个目录里没有 .jsonl 文件：%s" % args.目录)
        return 1

    print("找到 %d 个文件\n" % len(files))
    print("%-34s %6s %6s %7s  %s" % ("文件", "合格", "不合格", "字数", "备注"))
    print("-" * 86)

    good_all, seen, total_bad = [], set(), 0
    for path in files:
        name = os.path.basename(path)
        good, bad, chars = 0, [], 0
        with open(path, encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    bad.append((n, "不是合法 JSON（%s）" % str(e).split(":")[0]))
                    continue
                ok, why, _, c = check_sample(obj, args.min_len)
                if not ok:
                    bad.append((n, why))
                    continue
                key = json.dumps(obj, ensure_ascii=False, sort_keys=True)
                if key in seen and not args.allow_dup:
                    bad.append((n, "和前面某一条完全重复"))
                    continue
                seen.add(key)
                good_all.append(obj)
                good += 1
                chars += c

        total_bad += len(bad)
        note = "" if not bad else "见下"
        print("%-34s %6d %6d %7d  %s" % (name[:34], good, len(bad), chars, note))
        for n, why in bad[:6]:
            print("        └─ 第 %d 行：%s" % (n, why))
        if len(bad) > 6:
            print("        └─ …还有 %d 条问题" % (len(bad) - 6))

    print("-" * 86)
    rounds = Counter(len(s["messages"]) for s in good_all)
    print("\n合计：%d 条可用，%d 条被挡下。" % (len(good_all), total_bad))
    if rounds:
        print("轮数分布：" + "，".join("%d 轮 ×%d" % (k, v) for k, v in sorted(rounds.items())))

    if not args.write:
        print("\n（现在是体检模式，没有写文件。确认无误后加 --write 再跑一次）")
        return 0

    with open(args.output, "w", encoding="utf-8") as f:
        for s in good_all:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print("\n已写出：%s（%d 条）" % (args.output, len(good_all)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
