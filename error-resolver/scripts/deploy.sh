#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# deploy.sh — Build, push to ECR, and deploy Error Resolver on App Runner
#
# Usage:
#   ./scripts/deploy.sh [options]
#
# Options:
#   --region         AWS region                        (default: us-east-1)
#   --stack          CloudFormation stack name         (default: error-resolver)
#   --repo           ECR repository name               (default: error-resolver)
#   --tag            Docker image tag                  (default: latest)
#   --github-owner   GitHub repo owner / org           (required)
#   --github-repo    GitHub repository name            (required)
#   --oracle-host    RDS Oracle endpoint               (optional)
#   --oracle-svc     Oracle service name               (default: ORCL)
#   --secret-github  Secrets Manager secret for GitHub (default: error-resolver/github)
#   --secret-oracle  Secrets Manager secret for Oracle (default: error-resolver/oracle)
#   --secret-tavily  Secrets Manager secret for Tavily (default: error-resolver/tavily)
#   --model          GitHub Copilot model              (default: gpt-4o)
#   --cpu            App Runner CPU                    (default: "1 vCPU")
#   --memory         App Runner memory                 (default: "2 GB")
#   --skip-build     Skip Docker build+push (redeploy existing image)
#
# Prerequisites:
#   - AWS CLI v2 configured (aws configure)
#   - Docker running
#   - Secrets already created in Secrets Manager
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────
REGION="us-east-1"
STACK_NAME="error-resolver"
ECR_REPO="error-resolver"
IMAGE_TAG="latest"
GITHUB_OWNER=""
GITHUB_REPO_NAME=""
ORACLE_HOST=""
ORACLE_SVC="ORCL"
SECRET_GITHUB="error-resolver/github"
SECRET_ORACLE="error-resolver/oracle"
SECRET_TAVILY="error-resolver/tavily"
COPILOT_MODEL="gpt-4o"
CPU="1 vCPU"
MEMORY="2 GB"
SKIP_BUILD=false

# ── Parse arguments ───────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --region)        REGION="$2";        shift 2 ;;
    --stack)         STACK_NAME="$2";    shift 2 ;;
    --repo)          ECR_REPO="$2";      shift 2 ;;
    --tag)           IMAGE_TAG="$2";     shift 2 ;;
    --github-owner)  GITHUB_OWNER="$2";  shift 2 ;;
    --github-repo)   GITHUB_REPO_NAME="$2"; shift 2 ;;
    --oracle-host)   ORACLE_HOST="$2";   shift 2 ;;
    --oracle-svc)    ORACLE_SVC="$2";    shift 2 ;;
    --secret-github) SECRET_GITHUB="$2"; shift 2 ;;
    --secret-oracle) SECRET_ORACLE="$2"; shift 2 ;;
    --secret-tavily) SECRET_TAVILY="$2"; shift 2 ;;
    --model)         COPILOT_MODEL="$2"; shift 2 ;;
    --cpu)           CPU="$2";           shift 2 ;;
    --memory)        MEMORY="$2";        shift 2 ;;
    --skip-build)    SKIP_BUILD=true;    shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Validate required args ────────────────────────────────────────────
if [[ -z "$GITHUB_OWNER" || -z "$GITHUB_REPO_NAME" ]]; then
  echo "ERROR: --github-owner and --github-repo are required."
  echo "Example:"
  echo "  ./scripts/deploy.sh --github-owner my-org --github-repo my-app"
  exit 1
fi

# ── Derived values ────────────────────────────────────────────────────
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
ECR_IMAGE_URI="${ECR_REGISTRY}/${ECR_REPO}:${IMAGE_TAG}"

# Script is in error-resolver/scripts/ — repo root is two levels up
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"          # error-resolver/
CFN_TEMPLATE="${SCRIPT_DIR}/../cfn/apprunner-deploy.yaml"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Error Resolver — App Runner Deployment"
echo "═══════════════════════════════════════════════════════"
echo "  Account : $ACCOUNT_ID"
echo "  Region  : $REGION"
echo "  Stack   : $STACK_NAME"
echo "  Image   : $ECR_IMAGE_URI"
echo "═══════════════════════════════════════════════════════"
echo ""

# ── Step 1: Create ECR repository (idempotent) ────────────────────────
echo "▶ Step 1/4 — Ensuring ECR repository exists..."
aws ecr describe-repositories \
    --repository-names "$ECR_REPO" \
    --region "$REGION" \
    --output text > /dev/null 2>&1 || \
  aws ecr create-repository \
    --repository-name "$ECR_REPO" \
    --region "$REGION" \
    --image-scanning-configuration scanOnPush=true \
    --query 'repository.repositoryUri' \
    --output text
echo "   ECR repository: ${ECR_REGISTRY}/${ECR_REPO}"

# ── Step 2: Build and push Docker image ───────────────────────────────
if [[ "$SKIP_BUILD" == false ]]; then
  echo ""
  echo "▶ Step 2/4 — Building Docker image..."
  docker build --platform linux/amd64 -t "${ECR_REPO}:${IMAGE_TAG}" "$APP_DIR"

  echo ""
  echo "▶ Pushing to ECR..."
  aws ecr get-login-password --region "$REGION" | \
    docker login --username AWS --password-stdin "$ECR_REGISTRY"

  docker tag "${ECR_REPO}:${IMAGE_TAG}" "$ECR_IMAGE_URI"
  docker push "$ECR_IMAGE_URI"
  echo "   Pushed: $ECR_IMAGE_URI"
else
  echo ""
  echo "▶ Step 2/4 — Skipping build (--skip-build set)."
fi

# ── Step 3: Deploy CloudFormation stack ───────────────────────────────
echo ""
echo "▶ Step 3/4 — Deploying CloudFormation stack '${STACK_NAME}'..."

aws cloudformation deploy \
  --template-file "$CFN_TEMPLATE" \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ECRImageURI="$ECR_IMAGE_URI" \
    AwsSecretGithub="$SECRET_GITHUB" \
    AwsSecretOracle="$SECRET_ORACLE" \
    AwsSecretTavily="$SECRET_TAVILY" \
    GitHubRepoOwner="$GITHUB_OWNER" \
    GitHubRepoName="$GITHUB_REPO_NAME" \
    OracleHost="$ORACLE_HOST" \
    OracleServiceName="$ORACLE_SVC" \
    CopilotModel="$COPILOT_MODEL" \
    Cpu="$CPU" \
    Memory="$MEMORY"

# ── Step 4: Print outputs ─────────────────────────────────────────────
echo ""
echo "▶ Step 4/4 — Deployment complete!"
echo ""

APP_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='AppURL'].OutputValue" \
  --output text)

SERVICE_ARN=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ServiceArn'].OutputValue" \
  --output text)

echo "═══════════════════════════════════════════════════════"
echo "  App URL    : $APP_URL"
echo "  Service ARN: $SERVICE_ARN"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "  To redeploy after a code change:"
echo "  ./scripts/deploy.sh --github-owner $GITHUB_OWNER --github-repo $GITHUB_REPO_NAME --tag \$(git rev-parse --short HEAD)"
echo ""
echo "  App Runner auto-deploys when a new image is pushed to ECR."
echo ""
