#!/bin/sh
# Pin GitHub SSH host keys and pick a deploy-key identity.
# Source:  . scripts/github-ssh.sh
# Optional: GIT_SSH_KEY (private key body) or GIT_SSH_IDENTITY=/path/to/key

mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"
_github_hosts_file="${HOME}/.ssh/github_known_hosts"

# Official keys: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints
# Keep in sync with deploy/github_known_hosts.
cat >"${_github_hosts_file}" <<'EOF'
github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl
github.com ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg=
github.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk=
EOF
chmod 644 "${_github_hosts_file}"

# Actions can inject the Deploy key private key; persist it for later git fetch.
if [ -n "${GIT_SSH_KEY:-}" ]; then
	printf '%s' "$GIT_SSH_KEY" >"${HOME}/.ssh/github_deploy"
	[ -n "$(tail -c 1 "${HOME}/.ssh/github_deploy")" ] && printf '\n' >>"${HOME}/.ssh/github_deploy"
	chmod 600 "${HOME}/.ssh/github_deploy"
fi

_identity="${GIT_SSH_IDENTITY:-}"
if [ -z "${_identity}" ]; then
	for _candidate in "${HOME}/.ssh/bot-bw-deploy" "${HOME}/.ssh/github_deploy" "${HOME}/.ssh/id_ed25519" "${HOME}/.ssh/id_rsa"; do
		if [ -f "${_candidate}" ]; then
			_identity="${_candidate}"
			break
		fi
	done
fi

if [ -z "${_identity}" ]; then
	echo "github-ssh: no private key for git@github.com" >&2
	echo "Put the Deploy key at ~/.ssh/bot-bw-deploy or set secret GIT_SSH_KEY" >&2
	ls -la "${HOME}/.ssh" >&2 || true
	unset _identity _github_hosts_file _candidate
	return 1 2>/dev/null || exit 1
fi

export GIT_SSH_COMMAND="ssh -o UserKnownHostsFile=${_github_hosts_file} -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -i ${_identity}"
unset _identity _github_hosts_file _candidate
