import json
import shutil
import subprocess


def run_command(command):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
        )

        return {
            "command": " ".join(command),
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }

    except Exception as exc:
        return {
            "command": " ".join(command),
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc),
        }


print("=" * 60)
print("AGENT-REACH PAPER TRADER INTEGRATION TEST")
print("=" * 60)
print()

agent_reach = shutil.which("agent-reach")

if not agent_reach:
    print("RESULT: Agent-Reach is NOT installed.")
    print()
    print("This is expected if the environment has not been installed yet.")
    raise SystemExit(0)

print(f"Agent-Reach executable: {agent_reach}")
print()

version = run_command(["agent-reach", "version"])

print("--- VERSION ---")
print(version["stdout"] or version["stderr"])
print()

doctor = run_command(["agent-reach", "doctor", "--json"])

print("--- DOCTOR ---")

if doctor["stdout"]:
    try:
        data = json.loads(doctor["stdout"])
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except json.JSONDecodeError:
        print(doctor["stdout"])
else:
    print(doctor["stderr"])

print()

print("=" * 60)
print("TEST COMPLETE")
print("=" * 60)