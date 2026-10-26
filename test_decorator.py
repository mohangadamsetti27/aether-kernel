from kernel import AetherKernel, KernelDeadlockException

kernel = AetherKernel(max_steps=5, loop_threshold=2)

# Any developer can now add this single line above their tools:
@kernel.protect(agent_id="payment_worker")
def process_refund(order_id: str):
    return f"Refund initiated for {order_id}"

print("--- Running Protected Function ---")
try:
    for i in range(4):
        res = process_refund(order_id="ORD-9921")
        print(f"Step {i+1}: {res}")
except KernelDeadlockException as e:
    print(f"\n{e}")
    print("[✓] Decorator successfully intercepted and halted loop!")
