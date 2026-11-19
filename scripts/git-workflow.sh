#!/usr/bin/env bash
# Selene Git Workflow Helper
# Easily manage feature, fix, and hotfix branches.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

function usage() {
    echo "🌸 Selene Git Workflow Helper"
    echo ""
    echo "Usage:"
    echo "  ./scripts/git-workflow.sh start <feature|fix|hotfix|release|docs> <name>"
    echo "  ./scripts/git-workflow.sh check"
    echo "  ./scripts/git-workflow.sh release <version>"
    echo "  ./scripts/git-workflow.sh status"
    echo "  ./scripts/git-workflow.sh sync"
    echo ""
    echo "Examples:"
    echo "  ./scripts/git-workflow.sh start feature dynamic-waveform"
    echo "  ./scripts/git-workflow.sh start fix ptt-release-jitter"
    echo "  ./scripts/git-workflow.sh start hotfix audio-device-hang"
    echo "  ./scripts/git-workflow.sh release 2.5.0"
    echo "  ./scripts/git-workflow.sh check"
    exit 1
}

if [[ $# -lt 1 ]]; then
    usage
fi

COMMAND="$1"
cd "${REPO_ROOT}"

case "${COMMAND}" in
    start)
        if [[ $# -lt 3 ]]; then
            echo "❌ Error: Missing branch type or name."
            usage
        fi
        KIND="$2"
        NAME="$3"
        
        case "${KIND}" in
            feature|feat)
                BASE_BRANCH="develop"
                PREFIX="feature"
                ;;
            fix|bugfix)
                BASE_BRANCH="develop"
                PREFIX="fix"
                ;;
            hotfix)
                BASE_BRANCH="main"
                PREFIX="hotfix"
                ;;
            release)
                BASE_BRANCH="develop"
                PREFIX="release"
                ;;
            docs)
                BASE_BRANCH="develop"
                PREFIX="docs"
                ;;
            *)
                echo "❌ Unknown branch type: ${KIND}. Use feature, fix, hotfix, release, or docs."
                exit 1
                ;;
        esac

        BRANCH_NAME="${PREFIX}/${NAME}"
        echo "🌱 Creating branch '${BRANCH_NAME}' from base '${BASE_BRANCH}'..."
        git checkout "${BASE_BRANCH}"
        if git remote | grep -q "origin"; then
            echo "🔄 Pulling latest ${BASE_BRANCH} from origin..."
            git pull origin "${BASE_BRANCH}" || true
        fi
        git checkout -b "${BRANCH_NAME}"
        echo "✨ Switched to branch '${BRANCH_NAME}'. Happy coding, darling!"
        ;;

    check)
        echo "🔍 Running Selene pre-flight checks..."
        echo "1/3 Checking Python linting with Ruff..."
        uv run ruff check src tests
        
        echo "2/3 Running offline unit tests with Pytest..."
        uv run pytest -v
        
        echo "3/3 Compiling Swift HUD engine..."
        swift build --package-path hud
        
        echo "💖 All verification checks passed! You are ready to commit and push."
        ;;

    release)
        if [[ $# -lt 2 ]]; then
            echo "❌ Error: Missing release version (e.g. 2.5.0 or v2.5.0)."
            echo "Usage: ./scripts/git-workflow.sh release 2.5.0"
            exit 1
        fi
        RAW_VER="$2"
        VER="${RAW_VER#v}"
        TAG="v${VER}"

        echo "🌸 Preparing Release ${TAG}..."
        
        # 1. Ensure clean git status
        if [[ -n "$(git status --porcelain)" ]]; then
            echo "❌ Error: Working tree has uncommitted changes. Please commit or stash them first."
            exit 1
        fi

        # 2. Switch to main and sync
        echo "🌿 Switching to 'main' branch..."
        git checkout main
        if git remote | grep -q "origin"; then
            git pull origin main
        fi

        # 3. Update version in pyproject.toml
        echo "📝 Updating version in pyproject.toml to ${VER}..."
        sed -i '' -e "s/^version = .*/version = \"${VER}\"/" "${REPO_ROOT}/pyproject.toml"

        # 4. Run pre-flight checks
        echo "🔍 Running pre-flight checks before tagging..."
        ./scripts/git-workflow.sh check

        # 5. Commit and tag
        echo "🏷️ Creating release commit and git tag ${TAG}..."
        git commit -am "chore(release): bump version to ${TAG}"
        git tag -a "${TAG}" -m "Release ${TAG}"

        # 6. Push to origin
        echo "🚀 Pushing release commit and tag to GitHub..."
        git push origin main
        git push origin "${TAG}"

        # 7. Merge back to develop so version bump persists in integration
        echo "🔄 Merging release bump back to 'develop'..."
        git checkout develop
        git merge main
        git push origin develop

        echo ""
        echo "💖 Congratulations darling! ${TAG} has been released and pushed to GitHub."
        echo "   GitHub Actions is now compiling Selene.app and publishing your release assets at:"
        echo "   https://github.com/wlkcsh/selene/releases/tag/${TAG}"
        ;;

    status)
        CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
        echo "🌿 Current branch: ${CURRENT_BRANCH}"
        git status -s
        ;;

    sync)
        CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
        echo "🔄 Syncing '${CURRENT_BRANCH}'..."
        if git remote | grep -q "origin"; then
            git pull origin "${CURRENT_BRANCH}" || true
        else
            echo "ℹ️ No remote 'origin' configured yet."
        fi
        ;;

    *)
        usage
        ;;
esac
