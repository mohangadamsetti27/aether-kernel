from kernel import AetherKernel, KernelDeadlockException

kernel = AetherKernel(max_steps=8, loop_threshold=2)

shared_database = {"account_balance": 1000, "status": "active"}

def inspect_database(query: str):
    return f"Result for {query}: Current balance is {shared_database['account_balance']}"

def run_agent_simulation():
    agent_id = "test_agent_01"
    
    # 1. Take snapshot
    kernel.checkpoint(agent_id, "account_balance", shared_database["account_balance"])
    print(f"Initial State: {shared_database}\n")

    # 2. Simulate loop calls
    simulated_calls = [
        ("inspect_database", {"query": "user_balance"}),
        ("inspect_database", {"query": "user_balance"}),
        ("inspect_database", {"query": "user_balance"}),  # Breaker trips here
    ]

    try:
        for tool_name, args in simulated_calls:
            res = kernel.execute_tool(agent_id, tool_name, inspect_database, **args)
            print(f"   Output: {res}")
    except KernelDeadlockException as e:
        print(f"\n{e}")
        print("[!] Initiating automatic rollback to safe state...")
        restored = kernel.rollback(agent_id, "account_balance")
        shared_database["account_balance"] = restored
        print(f"[✓] State verified & intact: {shared_database}")

if __name__ == "__main__":
    run_agent_simulation()
