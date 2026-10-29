import subprocess
import time

print("\n🚀 STARTING YC BENCHMARK DEMO...\n")
time.sleep(1)

subprocess.run(["python3", "fragile_agent.py"])

print("\n\n...Now attaching Aether Kernel to the exact same workflow...\n\n")
time.sleep(2)

subprocess.run(["python3", "guarded_agent.py"])
