#!/usr/bin/env bash
set -euo pipefail

readonly DEFAULT_NAMESPACE="default"
readonly DEFAULT_CLUSTER="za-pg-16"

namespace="$DEFAULT_NAMESPACE"
cluster="$DEFAULT_CLUSTER"
context=""
output_path=""
database=""
temporary_output=""

usage() {
  cat <<'EOF'
Usage: backup-database.sh [OPTIONS] DATABASE

Back up one database from the primary pod of a Zalando Postgres cluster.
The result is a PostgreSQL custom-format archive suitable for pg_restore.

Options:
  -o, --output PATH      Output path (default: ./DATABASE_TIMESTAMP.dump)
  -n, --namespace NAME   Kubernetes namespace (default: default)
  -c, --cluster NAME     Zalando cluster name (default: za-pg-16)
      --context NAME     kubectl context to use
  -h, --help             Show this help

Environment:
  KUBECTL                 kubectl executable (default: kubectl)

The output path must not already exist. Partial output is removed on failure.
EOF
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  if [[ -n "$temporary_output" && -e "$temporary_output" ]]; then
    rm -f -- "$temporary_output" || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

while (($# > 0)); do
  case "$1" in
    -o|--output)
      (($# >= 2)) || die "$1 requires a path"
      output_path=$2
      shift 2
      ;;
    --output=*)
      output_path=${1#*=}
      shift
      ;;
    -n|--namespace)
      (($# >= 2)) || die "$1 requires a namespace"
      namespace=$2
      shift 2
      ;;
    --namespace=*)
      namespace=${1#*=}
      shift
      ;;
    -c|--cluster)
      (($# >= 2)) || die "$1 requires a cluster name"
      cluster=$2
      shift 2
      ;;
    --cluster=*)
      cluster=${1#*=}
      shift
      ;;
    --context)
      (($# >= 2)) || die "$1 requires a context name"
      context=$2
      shift 2
      ;;
    --context=*)
      context=${1#*=}
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      [[ -z "$database" ]] || die "exactly one database name is required"
      (($# == 1)) || die "exactly one database name is required"
      database=$1
      shift
      ;;
    -*)
      die "unknown option: $1"
      ;;
    *)
      [[ -z "$database" ]] || die "exactly one database name is required"
      database=$1
      shift
      ;;
  esac
done

[[ -n "$database" ]] || die "a database name is required"
[[ -n "$namespace" ]] || die "namespace must not be empty"
[[ -n "$cluster" ]] || die "cluster name must not be empty"

# These values are interpolated into a Kubernetes label selector. Restrict them
# to the label-value syntax instead of allowing selector operators.
[[ "$cluster" =~ ^[[:alnum:]]([[:alnum:]_.-]{0,61}[[:alnum:]])?$ ]] ||
  die "invalid cluster label value: $cluster"
[[ "$namespace" =~ ^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$ ]] ||
  die "invalid Kubernetes namespace: $namespace"

kubectl_bin=${KUBECTL:-kubectl}
command -v "$kubectl_bin" >/dev/null 2>&1 || die "kubectl executable not found: $kubectl_bin"

kubectl_cmd=("$kubectl_bin")
if [[ -n "$context" ]]; then
  kubectl_cmd+=(--context "$context")
fi

if [[ -z "$output_path" ]]; then
  safe_database=${database//[!a-zA-Z0-9_.-]/_}
  timestamp=$(date '+%Y%m%dT%H%M%S')
  output_path="./${safe_database}_${timestamp}.dump"
fi

output_directory=$(dirname -- "$output_path")
[[ -d "$output_directory" ]] || die "output directory does not exist: $output_directory"
[[ ! -e "$output_path" && ! -L "$output_path" ]] || die "output already exists: $output_path"

selector="application=spilo,cluster-name=${cluster},spilo-role=master"
printf 'Locating primary pod for %s/%s...\n' "$namespace" "$cluster" >&2

if ! pod_output=$("${kubectl_cmd[@]}" get pods \
  --namespace "$namespace" \
  --selector "$selector" \
  --field-selector 'status.phase=Running' \
  --output 'jsonpath={range .items[*]}{.metadata.name}{"\n"}{end}'); then
  die "failed to query pods"
fi

pods=()
while IFS= read -r pod_name; do
  [[ -n "$pod_name" ]] && pods+=("$pod_name")
done <<< "$pod_output"

((${#pods[@]} > 0)) || die "no running primary Spilo pod found for cluster $cluster"
((${#pods[@]} == 1)) || die "multiple running primary Spilo pods found: ${pods[*]}"
primary_pod=${pods[0]}

printf 'Checking database %s on pod %s...\n' "$database" "$primary_pod" >&2
if ! recovery_state=$("${kubectl_cmd[@]}" exec \
  --namespace "$namespace" \
  "$primary_pod" \
  --container postgres \
  -- psql \
  --username=postgres \
  --dbname="$database" \
  --no-password \
  --no-align \
  --tuples-only \
  --command='SELECT pg_is_in_recovery()'); then
  die "cannot connect to database $database on pod $primary_pod"
fi

recovery_state=${recovery_state//$'\r'/}
recovery_state=${recovery_state//$'\n'/}
[[ "$recovery_state" == "f" ]] || die "selected pod is not the writable primary"

umask 077
temporary_output=$(mktemp --tmpdir="$output_directory" ".$(basename -- "$output_path").partial.XXXXXX")

printf 'Backing up %s to %s...\n' "$database" "$output_path" >&2
if ! "${kubectl_cmd[@]}" exec \
  --namespace "$namespace" \
  "$primary_pod" \
  --container postgres \
  -- pg_dump \
  --username=postgres \
  --dbname="$database" \
  --no-password \
  --format=custom > "$temporary_output"; then
  die "pg_dump failed; partial output has been removed"
fi

[[ -s "$temporary_output" ]] || die "pg_dump produced an empty archive"
archive_magic=$(LC_ALL=C head -c 5 -- "$temporary_output")
[[ "$archive_magic" == "PGDMP" ]] || die "pg_dump output is not a custom-format archive"

# A hard link publishes the completed archive atomically and refuses to replace
# a path that appeared while pg_dump was running.
if ! ln -- "$temporary_output" "$output_path"; then
  die "could not publish backup without overwriting: $output_path"
fi
rm -f -- "$temporary_output"
temporary_output=""

archive_size=$(wc -c < "$output_path")
printf 'Backup complete: %s (%s bytes)\n' "$output_path" "$archive_size"
