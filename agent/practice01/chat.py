import configparser

import requests


def load_config(path="config.ini"):
    conf = configparser.ConfigParser()
    conf.read(path, encoding="utf-8")
    return conf["llm"]


def ask_llm(cfg, history):
    """带聊天记录请求LLM，并以打字机效果流式输出"""
    payload = {
        "model": cfg["model"],
        "messages": history,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }

    url = cfg["api_url"].rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"

    resp = requests.post(
        url, json=payload, headers=headers,
        stream=True, timeout=cfg.getint("timeout"),
    )
    resp.raise_for_status()

    answer = ""
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if data == "[DONE]":
            break
        import json
        delta = json.loads(data)["choices"][0]["delta"]
        piece = delta.get("content") or ""
        print(piece, end="", flush=True)  # 打字机效果
        answer += piece
    print()  # 回答结束后换行
    return answer


def main():
    cfg = load_config()
    history = []  # 保存所有聊天记录

    while True:  # 无限循环，按 Ctrl+C 退出
        question = input("请输入问题：")
        history.append({"role": "user", "content": question})
        answer = ask_llm(cfg, history)
        history.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已退出。")