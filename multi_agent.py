import threading
import time
from locks import AgentLockManager

lock_mgr = AgentLockManager()

def worker_agent(agent_name: str, delay: float):
    resource = "shared_bank_account_01"
    print(f"[{agent_name}] Attempting to lock {resource}...")
    
    acquired = lock_mgr.acquire(resource_id=resource, agent_id=agent_name, timeout=3.0)
    
    if acquired:
        print(f"--> [{agent_name}] Lock ACQUIRED. Modifying balance...")
        time.sleep(delay)
        lock_mgr.release(resource_id=resource, agent_id=agent_name)
        print(f"<-- [{agent_name}] Work complete. Lock RELEASED.")
    else:
        print(f"[x] [{agent_name}] Lock REJECTED! Another agent is currently modifying this resource.")

t1 = threading.Thread(target=worker_agent, args=("Agent_Alpha", 1.5))
t2 = threading.Thread(target=worker_agent, args=("Agent_Bravo", 0.5))

t1.start()
time.sleep(0.1)  # Stagger slightly so Alpha acquires first
t2.start()

t1.join()
t2.join()
