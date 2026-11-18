import os, sys, subprocess, threading, queue, time, pathlib, json, tkinter as tk
from PIL import ImageGrab, Image, ImageChops
dest=pathlib.Path('photos')
dest.mkdir(exist_ok=True)
root=tk.Tk()
root.title('LambChat | Native display verification')
w,h=root.winfo_screenwidth(),root.winfo_screenheight()
root.geometry(f'{int(w*.78)}x{int(h*.65)}+{int(w*.11)}+{int(h*.20)}')
root.configure(bg='#faf9f5')
tk.Label(root,text='Computer Use   /   Display verification',font=('Helvetica',24),fg='#222b35',bg='#faf9f5').pack(anchor='w',padx=32,pady=24)
tk.Label(root,text='Native test window     •     These four reference regions stay visible throughout the session.',bg='#faf9f5',fg='#384751').pack(anchor='w',padx=32)
grid=tk.Frame(root,bg='#faf9f5')
grid.pack(fill='both',expand=True,padx=28,pady=20)
colors=['#94bfc1','#d9b38e','#a9b2d3','#a8c09b']
for i,c in enumerate(colors):
    grid.rowconfigure(i//2,weight=1)
    grid.columnconfigure(i%2,weight=1)
    tk.Label(grid,text=['Upper left','Upper right','Lower left','Lower right'][i],bg=c,fg='#17262c',font=('Helvetica',18)).grid(row=i//2,column=i%2,sticky='nsew',padx=4,pady=4)
def paint(t):
    end=time.monotonic()+t
    while time.monotonic()<end:
        root.update()
        time.sleep(.02)
def snap(name):
    file=dest/(name+'.png')
    if sys.platform=='darwin':
        subprocess.run(['screencapture','-x','-D','1',str(file)],check=True)
    else:
        ImageGrab.grab(include_layered_windows=True).save(file)
    img=Image.open(file).convert('RGB')
    hist=img.resize((160,100)).getdata()
    for c in colors:
        rgb=bytes.fromhex(c[1:])
        assert sum(max(abs(a-b) for a,b in zip(p,rgb))<18 for p in hist)>80,(name,c,img.size)
    print(name,img.size,flush=True)
paint(1)
snap('01-before')
exe=next(p for p in pathlib.Path('frontend/src-tauri/target/debug/examples').glob('desktop_control_smoke*') if p.name in ('desktop_control_smoke', 'desktop_control_smoke.exe'))
exe.chmod(0o755)
def run(auto):
    env=dict(os.environ,LAMBCHAT_CONTROL_TEST_ROOT=os.getcwd(),LAMBCHAT_CONTROL_TEST_PYTHON=sys.executable)
    if auto: env['LAMBCHAT_CONTROL_AUTOMATED']='1'
    p=subprocess.Popen([str(exe.resolve())],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=env)
    lines=queue.Queue()
    def reader():
        for line in p.stdout:
            lines.put(line.strip())
    threading.Thread(target=reader,daemon=True).start()
    until=time.monotonic()+125
    caught=False
    try:
        while time.monotonic()<until:
            paint(.025)
            while not lines.empty():
                line=lines.get()
                print(line,flush=True)
                if not caught and ('"phase":"paused"' in line if auto else '"state": "active"' in line):
                    paint(.15 if auto else .65)
                    snap('03-paused' if auto else '02-active')
                    caught=True
                    if not auto: return
            if p.poll() is not None:
                assert p.returncode==0 and caught,(p.returncode,caught)
                return
        raise TimeoutError('native state')
    finally:
        if p.poll() is None:
            if os.name=='nt': subprocess.run(['taskkill','/f','/t','/pid',str(p.pid)],check=False)
            else: p.terminate()
            p.wait(timeout=10)
run(False)
paint(1)
run(True)
paint(.5)
snap('04-ended')

baseline,active,paused=[Image.open(dest/n).convert("RGB") for n in ("01-before.png","02-active.png","03-paused.png")]
width=min(active.width,1440)
roi=(width//2-202,26,width//2+202,124)
def changes(first, second):
    delta=ImageChops.difference(first.crop(roi),second.crop(roi))
    return sum(max(px)>24 for px in delta.getdata())
assert changes(baseline,active)>1500, "Running control missing from screenshot"
assert changes(active,paused)>1500, "Paused control missing from screenshot"
