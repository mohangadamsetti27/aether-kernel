import time

print("\n" + "=" * 70)
print("  STEP 1: THE UNPROTECTED AGENT (Without Kernel)")
print("=" * 70)
print("Agent Goal: 'Book seat 14B on Indigo 6E-204 for ₹4,500'\n")

def book_ticket_api(flight: str, seat: str, amount: int):
    time.sleep(0.05)
    return {"status": "error", "code": 504, "message": "Gateway Timeout: Payment unconfirmed"}

def llm_decide(observation):
    return {"tool": "book_ticket_api", "args": {"flight": "6E-204", "seat": "14B", "amount": 4500}}

tokens_burned = 0
total_money_risked = 0
step = 0
start_time = time.perf_counter()

while step < 5:
    step += 1
    tokens_burned += 420
    total_money_risked += 4500
    
    print(f"👉 [Agent Cycle {step}] LLM deciding next action...")
    decision = llm_decide(None)
    print(f"   Action: Calling {decision['tool']}(seat='{decision['args']['seat']}', amount={decision['args']['amount']})")
    
    resp = book_ticket_api(**decision['args'])
    print(f"   API Response: {resp['message']}")
    print(f"   ⚠️  CRITICAL: Agent retrying identically! Tokens wasted: {tokens_burned} | Money at risk: ₹{total_money_risked}\n")
    time.sleep(0.3)

print("❌ STATUS: RUNAWAY LOOP DETECTED")
print(f"   • Total Tokens Burned: {tokens_burned}")
print(f"   • Unhandled API Retries: {step} attempts")
print(f"   • Total Time Wasted: {(time.perf_counter() - start_time)*1000:.2f}ms")
print("   • System State: CORRUPTED / UNCONFIRMED CHARGES")
print("=" * 70)
