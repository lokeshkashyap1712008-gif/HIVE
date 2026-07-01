# Ollama Optimization for RTX 3050 6GB + 12GB RAM
# Your hardware: 6GB VRAM, ~6GB free RAM
# gemma4:e2b-it-q4_K_M = 7.16GB (won't fully fit in VRAM, will use RAM too)

# === SETTINGS TO APPLY ===

# GPU layers — set 24 out of ~36 layers on GPU, rest on RAM
export OLLAMA_GPU_LAYERS=24

# Max parallel requests (your VRAM is limited, don't overload)
export OLLAMA_NUM_PARALLEL=2

# Only one model loaded at a time (your RAM is limited)
export OLLAMA_MAX_LOADED_MODELS=1

# Flash attention — faster, uses less VRAM
export OLLAMA_FLASH_ATTENTION=1

# === HOW TO USE ===
# Option A: Set in ~/.bashrc or ~/.zshrc (persistent):
echo 'export OLLAMA_GPU_LAYERS=24' >> ~/.bashrc
echo 'export OLLAMA_NUM_PARALLEL=2' >> ~/.bashrc
echo 'export OLLAMA_FLASH_ATTENTION=1' >> ~/.bashrc
source ~/.bashrc

# Option B: Set per-session before running:
# OLLAMA_GPU_LAYERS=24 ollama run gemma4:e2b-it-q4_K_M

# Option C: Create config file at:
# Linux/Mac: ~/.ollama/config
# Git Bash/Windows: /c/Users/lokes/.ollama/config
# Add lines:
# OLLAMA_GPU_LAYERS=24
# OLLAMA_NUM_PARALLEL=2

# === VERIFY GPU IS BEING USED ===
# Run this to check if GPU is being used:
# nvidia-smi while running Ollama — you should see GPU memory used

# === PERFORMANCE NOTES FOR gemma4:e2b-it-q4_K_M ===
# This is a 2B parameter model with Q4 quantization
# Pros:  Very fast, runs locally, free, parallelizable
# Cons:  Limited reasoning depth for complex multi-step tasks
#        7GB model running on 6GB VRAM will use RAM offload = slower
#
# EXPECTED SPEEDS (approximate):
#   Simple task (Web Scout report generation):  1-3 seconds
#   Medium task (Report Agent structured output): 3-8 seconds
#   Complex task (Code Architect multi-file):   10-30 seconds
#
# For comparison, minimax via API:
#   Same tasks: likely faster but costs money
#   More reliable reasoning quality
#
# RECOMMENDATION: Use gemma4 for parallel workers (fast, stateless)
#                 Use minimax for Leader, Judge, Safety (quality matters)