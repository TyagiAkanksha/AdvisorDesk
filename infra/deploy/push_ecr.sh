#!/usr/bin/env bash
set -euo pipefail

# infra/deploy/push_ecr.sh — build, tag, and push AdvisorDesk's three container
# images (api, admin, client) to Amazon ECR (phase-6 task-02, AWS deployment).
#
# WHAT THIS SCRIPT DOES: builds each image locally with Docker, tags it TWICE
# (`latest` and the current git short SHA, e.g. `a1b2c3d`), creates the ECR
# repository the first time it's needed, and pushes both tags. That's all —
# it never touches the EC2 host, DNS, or any runtime environment variable.
# See infra/deploy/ec2-single-host.md for the next step (pulling the pushed
# images onto the deployed host).
#
# WHY TWO TAGS: `latest` is easy to reference while clicking through setup;
# the git-sha tag is what you actually want the deployed compose file pinned
# to, so a later `git checkout` + rebuild can never silently change what a
# running service serves out from under you.
#
# Beginner notes:
#   - This script BUILDS on the machine it runs on (your laptop, or a CI
#     runner) and then PUSHES the finished image — nothing is built inside
#     AWS. Docker must be running locally.
#   - You need the AWS CLI v2 already configured with credentials
#     (`aws configure`, or exported AWS_* env vars / an SSO profile) that can
#     create/describe ECR repositories and push images in the target account.
#   - Re-running this script is safe: it never fails just because a repo or
#     tag already exists (see "idempotent" notes inline below).
#
# Usage:
#   AWS_ACCOUNT_ID=123456789012 ./infra/deploy/push_ecr.sh
#   AWS_ACCOUNT_ID=123456789012 AWS_REGION=us-east-1 ./infra/deploy/push_ecr.sh
#
# Env vars:
#   AWS_ACCOUNT_ID   REQUIRED — your 12-digit AWS account id. The script
#                    fails fast with a clear message if this is unset.
#   AWS_REGION       optional — default "us-east-1" (the region pinned by the
#                    task-02 brief for this deployment).
#   API_PUBLIC_URL   optional — the production API origin baked into the two
#                    frontend images' build args (NEXT_PUBLIC_API_URL for
#                    admin; NEXT_PUBLIC_API_URL + API_URL for client — see
#                    infra/Dockerfile.web's own comments on why both frontend
#                    images need these as BUILD-time args, not just runtime
#                    env vars). Default:
#                    "https://api.advisordesk.tyagiakanksha.com" — AdvisorDesk's
#                    pinned production API domain (task-02 brief). Override
#                    only if you're building images for a different
#                    environment (e.g. a staging domain).

# ---------------------------------------------------------------------------
# Phase 0: read + validate inputs
# ---------------------------------------------------------------------------
if [[ -z "${AWS_ACCOUNT_ID:-}" ]]; then
  echo "ERROR: AWS_ACCOUNT_ID is required (your 12-digit AWS account id)." >&2
  echo "  Example: AWS_ACCOUNT_ID=123456789012 $0" >&2
  exit 1
fi

AWS_REGION="${AWS_REGION:-us-east-1}"
API_PUBLIC_URL="${API_PUBLIC_URL:-https://api.advisordesk.tyagiakanksha.com}"

# Resolve the repo root from this script's own location (infra/deploy/ -> infra/ -> repo root)
# rather than the caller's current directory, so this script works no matter where you run it
# from. This matters because BOTH Dockerfiles must be built with the REPO ROOT as the Docker
# build context: infra/Dockerfile.api's COPY lines read `apps/api/...`, and infra/Dockerfile.web's
# read `apps/${APP}` plus the pnpm workspace root manifests — neither resolves correctly from
# infra/ itself. infra/docker-compose.yml builds both the same way (`context: ..`, `dockerfile:
# infra/Dockerfile.*`) — this script mirrors that exactly.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

GIT_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "== AdvisorDesk: build + push images to ECR =="
echo "  account:        $AWS_ACCOUNT_ID"
echo "  region:         $AWS_REGION"
echo "  registry:       $ECR_REGISTRY"
echo "  git sha tag:    $GIT_SHA"
echo "  repo root:      $REPO_ROOT"
echo "  api url baked into frontend builds: $API_PUBLIC_URL"
echo

# ---------------------------------------------------------------------------
# Phase 1: ECR login
# ---------------------------------------------------------------------------
# One login is enough for all three repos below — they all live in the same
# account + region, hence the same registry hostname.
echo "-- Logging in to ECR ($ECR_REGISTRY)..."
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

# ---------------------------------------------------------------------------
# Phase 2: ensure each ECR repository exists (idempotent)
# ---------------------------------------------------------------------------
# `describe-repositories` first, `create-repository` only on a miss — running
# this script again against repos that already exist is a no-op here, never
# an error.
ensure_repo() {
  local repo_name="$1"
  if aws ecr describe-repositories --region "$AWS_REGION" --repository-names "$repo_name" \
    >/dev/null 2>&1; then
    echo "-- ECR repo already exists: $repo_name"
  else
    echo "-- Creating ECR repo: $repo_name"
    aws ecr create-repository --region "$AWS_REGION" --repository-name "$repo_name" >/dev/null
  fi
}

ensure_repo "advisordesk/api"
ensure_repo "advisordesk/admin"
ensure_repo "advisordesk/client"

# ---------------------------------------------------------------------------
# Phase 3: build, tag, push each image
# ---------------------------------------------------------------------------
# build_tag_push <ecr repo name> <dockerfile, relative to repo root> [extra `docker build` args...]
#
# Builds ONCE, tags the same build TWICE (`latest` + the git sha) so pushing
# both never re-builds — `docker build -t a -t b` attaches both tags to one
# image id.
build_tag_push() {
  local repo_name="$1"
  local dockerfile="$2"
  shift 2
  local image_uri="${ECR_REGISTRY}/${repo_name}"

  echo
  echo "-- Building $repo_name from $dockerfile (context: $REPO_ROOT)"
  docker build \
    -f "$REPO_ROOT/$dockerfile" \
    -t "${image_uri}:latest" \
    -t "${image_uri}:${GIT_SHA}" \
    "$@" \
    "$REPO_ROOT"

  echo "-- Pushing ${image_uri}:latest"
  docker push "${image_uri}:latest"
  echo "-- Pushing ${image_uri}:${GIT_SHA}"
  docker push "${image_uri}:${GIT_SHA}"
}

# api: no build args. infra/Dockerfile.api's own top-of-file comment: runtime config is
# env-only (DATABASE_URL, NVIDIA_API_KEY, ...) — nothing is baked into this image at build time.
build_tag_push "advisordesk/api" "infra/Dockerfile.api"

# admin: NEXT_PUBLIC_API_URL is a BUILD-time arg — infra/Dockerfile.web's own top comment:
# Next.js inlines NEXT_PUBLIC_* vars into the JS bundle at `next build` time, so this is baked
# into the image, not read at container start. ONE IMAGE PER ENVIRONMENT: if the API's public
# origin ever changes, this image must be rebuilt and repushed — restarting the running
# container changes nothing.
build_tag_push "advisordesk/admin" "infra/Dockerfile.web" \
  --build-arg "APP=admin" \
  --build-arg "NEXT_PUBLIC_API_URL=${API_PUBLIC_URL}"

# client: needs BOTH build args, and NEITHER is optional. NEXT_PUBLIC_API_URL is a BUILD-TIME
# bake exactly like admin's — apps/client/src/components/chat/useChatStream.ts's
# resolveApiBaseUrl() reads process.env.NEXT_PUBLIC_API_URL at module load and uses it for the
# browser-side fetch(`${...}/api/v1/public/chat`) that drives the entire client chat feature; it
# is load-bearing, not unused. API_URL backs apps/client/src/lib/publicApi.ts's server-only
# fetches — `next build` itself calls that code during its "Generating static pages" step, so
# API_URL needs a real value at BUILD time here too, same as NEXT_PUBLIC_API_URL. (The deployed
# client container ALSO needs API_URL set as a plain runtime environment variable, for
# the same module's per-request calls after the container starts — that's a separate step, not
# this script's job; see frontends.md's wiring section + ec2-single-host.md.) Because NEXT_PUBLIC_API_URL is baked at build time same
# as admin's, changing the API's public origin later requires rebuilding+repushing THIS image
# too — updating only the client service's runtime API_URL is not enough; see frontends.md.
build_tag_push "advisordesk/client" "infra/Dockerfile.web" \
  --build-arg "APP=client" \
  --build-arg "NEXT_PUBLIC_API_URL=${API_PUBLIC_URL}" \
  --build-arg "API_URL=${API_PUBLIC_URL}"

echo
echo "== Done. =="
echo "Pushed tags 'latest' and '${GIT_SHA}' to all three repos:"
echo "  ${ECR_REGISTRY}/advisordesk/api"
echo "  ${ECR_REGISTRY}/advisordesk/admin"
echo "  ${ECR_REGISTRY}/advisordesk/client"
echo
echo "Next: infra/deploy/ec2-single-host.md (pull + run all three images on the EC2 host)."
