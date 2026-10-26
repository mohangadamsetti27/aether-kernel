import json
import requests
from kernel import AetherKernel, KernelDeadlockException, KernelBudgetException

OLLAMA_API = "http://127.0.0.1:11434/api/generate"
MODEL = "qwen2.5-coder:1.5b"

# Configure Kernel with a tight token cap (e.g., 350 tokens) to test containment
kernel = AetherKernel(max_steps=5, max_tokens=350, loop_threshold=2)

user_account = {"balance": 500, "status": "active"}

def check_balance():
    return f"Current balance: ${user_account['balance']}"

def add_funds(amount: int):
    user_account["balance"] += amount
    return f"New balance: ${user_account['balance']}"

TOOLS = {
    "check_balance": check_balance,
    "add_funds": add_funds
}

def ask_local_llm(prompt: str) -> dict:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "format": "json",
        "stream": False
    }
    response = requests.post(OLLAMA_API, json=payload).json()
    tokens = response.get("eval_count", 0) + response.get("prompt_eval_count", 0)
    kernel.record_token_usage("agent_core", tokens)
    return json.loads(response["response"])

def run_agent():
    agent_id = "agent_core"
    kernel.checkpoint(agent_id, "balance", user_account["balance"])
    
    system_prompt = """
    You are an autonomous money agent. Always reply in JSON format with:
    {"tool": "check_balance", "args": {}} OR {"tool": "add_funds", "args": {"amount": 50}}
    """
    
    print(f"Starting balance: {user_account}\n")

    try:
        for i in range(4):
            print(f"--- Querying {MODEL} ---")
            action = ask_local_llm(f"{system_prompt}\nTask: check balance then add funds.")
            
            tool_name = action.get("tool")
            args = action.get("args", {})

            if tool_name in TOOLS:
                output = kernel.execute_tool(agent_id, tool_name, TOOLS[tool_name], **args)
                print(f"   Tool Result: {output}")

    except KernelBudgetException as e:
        print(f"\n{e}")
        print("[!] Kernel triggered automatic circuit protection due to token ceiling.")
    except KernelDeadlockException as e:
        print(f"\n{e}")
        print("[!] Kernel prevented infinite reasoning loop.")

    print(f"\nFinal State: {user_account}")

if __name__ == "__main__":
    run_agent()
