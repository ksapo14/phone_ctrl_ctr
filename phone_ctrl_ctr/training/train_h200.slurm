#!/usr/bin/env bash
#SBATCH --job-name=phone-functiongemma
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=1
#SBATCH --gpus-per-node=8
#SBATCH --cpus-per-task=16
#SBATCH --time=02:00:00
#SBATCH --output=functiongemma-%j.log
# Add your cluster's partition/account directives when submitting.
set -euo pipefail

# Submit from the project root after activating a shared Python environment.
# Model cache, data, environment and output must be accessible on every node.
export OMP_NUM_THREADS=2
export TOKENIZERS_PARALLELISM=false
export MASTER_ADDR
MASTER_ADDR=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -n 1)
export MASTER_PORT="${MASTER_PORT:-29500}"
export GPUS_PER_NODE="${GPUS_PER_NODE:-8}"
export TRAIN_OUTPUT="${TRAIN_OUTPUT:-training/runs/h200-${SLURM_JOB_ID}}"

srun --ntasks="$SLURM_NNODES" --ntasks-per-node=1 bash -c '
  exec torchrun --nnodes="$SLURM_NNODES" --nproc-per-node="$GPUS_PER_NODE" \
    --node-rank="$SLURM_PROCID" --master-addr="$MASTER_ADDR" --master-port="$MASTER_PORT" \
    training/train.py --output "$TRAIN_OUTPUT" --batch-size 2 --grad-accum 1 "$@"
' bash "$@"
