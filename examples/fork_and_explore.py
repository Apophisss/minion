"""Fork a desktop before a risky step, try two approaches in parallel, keep the winner."""

from minion import Desktop

base = Desktop.create("dev", name="project")
base.run(
    "mkdir -p ~/work/app && cd ~/work/app && git init -q && echo 'print(1)' > main.py && git add -A "
    "&& git -c user.name=a -c user.email=a@b commit -qm init"
)

a = base.fork("try-a")
b = base.fork("try-b")
a.run("cd ~/work/app && echo 'print(2)' > main.py")
b.run("cd ~/work/app && rm main.py")

for desk in (a, b):
    ok = desk.run("cd ~/work/app && python3 main.py").ok
    print(desk.name, "works" if ok else "broke")

b.remove()  # discard the failed branch
print("Kept", a.name, "and", base.name)
