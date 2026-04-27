import sys,json,os,sqlite3,random,threading
try: import serial; HAS_SERIAL=True
except: HAS_SERIAL=False
from PyQt6.QtWidgets import *
from PyQt6.QtGui import QPainter,QColor,QPen,QIcon,QPixmap,QTransform
from PyQt6.QtCore import Qt,QSize,QTimer

M2,M=r"module2\media",r"module1\media"
MAP_FILE,TMPL_FILE,DB_FILE=r"map.json",r"template.json",r"traffic.db"
LOGO=f"{M}\\TLgreen.png"
IMG1,IMG2,IMG3,IMG4,IMG5=f"{M}\\Cbottom.png",f"{M}\\Pedestrain.png",f"{M}\\Block.png",f"{M}\\Zhorizontal.png",f"{M}\\TLyellow.png"
PLACE_IMGS=[IMG1,IMG2,IMG3,IMG4,IMG5]; FREE={IMG2,IMG3}; ROT={IMG2,IMG4}
CYCLES={IMG1:[IMG1,f"{M}\\BCvertical.png",f"{M}\\GCicon.ico"],IMG3:[IMG3,f"{M}\\Stop.png",f"{M}\\Start.png"],IMG5:[IMG5,f"{M}\\TLred.png",f"{M}\\TLgreen.png"]}
TL_CYCLE=[f"{M}\\TLred.png",f"{M}\\TLyellow.png",f"{M}\\TLgreen.png"]
TL_STOP={f"{M}\\TLred.png"}; TL_G,TL_R,TL_Y=f"{M}\\TLgreen.png",f"{M}\\TLred.png",f"{M}\\TLyellow.png"
DIR_IMG={(1,0):f"{M2}\\Cright.png",(0,1):f"{M2}\\Cbottom.png",(-1,0):f"{M2}\\Cleft.png",(0,-1):f"{M2}\\Cvertical.png"}
BLOCK={f"{M2}\\Block.png",f"{M2}\\Stop.png"}; DIRS=[(1,0),(-1,0),(0,1),(0,-1)]; CELL,COLS,ROWS=36,21,21
AUTO_MODES={"Старт/Стоп цикла","Режим по времени","Режим по транспорту","Тест шаблон","Тест рандом"}
TL_MAP={"Диагностика":"Сброс","Восстановление":"Восстановление","Режим по времени":"По времени","Режим по транспорту":"По транспорту","Тест шаблон":"Тест шаблон","Тест рандом":"Тест рандом"}
ROUTES={}; TICK=0; TL_STATS={}; CAR_STATS={}; ARD=None

class Arduino:
    def __init__(self,port):
        self._s=None; self._cb=None
        if HAS_SERIAL and port:
            try: self._s=serial.Serial(port,9600,timeout=0.1); threading.Thread(target=self._read,daemon=True).start()
            except: pass
    def send(self,c):
        try: self._s and self._s.write(c.encode())
        except: pass
    def tl(self,path): self.send("G" if "green" in path else("R" if "red" in path else "Y"))
    def set_cb(self,cb): self._cb=cb
    def _read(self):
        while True:
            try:
                if self._s and self._s.in_waiting:
                    line=self._s.readline().decode().strip()
                    if self._cb and line: self._cb(line)
            except: pass

def db(sql,a=()): con=sqlite3.connect(DB_FILE); con.execute(sql,a); con.commit(); con.close()
def init_db(reset=False):
    db("CREATE TABLE IF NOT EXISTS Traffic_light (Id_light,Car_count_full_run,Car_average_in_minute,Count_color_switches)")
    db("CREATE TABLE IF NOT EXISTS Cars_stats (Car_id,Car_spawn_ticks,Car_exit_ticks)")
    if reset: db("DELETE FROM Traffic_light"); db("DELETE FROM Cars_stats")
def db_spawn(i): CAR_STATS[i]=TICK
def db_exit(i):
    if i in CAR_STATS: db("INSERT INTO Cars_stats VALUES(?,?,?)",(i,CAR_STATS.pop(i),TICK))
def db_tl(tid,key): TL_STATS.setdefault(tid,{"n":0,"sw":0,"t":TICK})[key]+=1
def db_flush():
    if not TL_STATS: return
    con=sqlite3.connect(DB_FILE)
    con.executemany("INSERT OR REPLACE INTO Traffic_light VALUES(?,?,?,?)",
        [(t,s["n"],round(s["n"]/max((TICK-s["t"])*0.4/60,.001),2),s["sw"]) for t,s in TL_STATS.items()])
    con.commit(); con.close()

get_px=lambda p,r=0:(lambda px:px.transformed(QTransform().rotate(r)) if r and not px.isNull() else px)(QPixmap(p))
new_obj=lambda p:{"path":p,"base":p,"rot":0,"speed":0}
load_j=lambda p:(json.load(open(p,encoding="utf-8")) if os.path.exists(p) else {})
save_j=lambda p,d:json.dump(d,open(p,"w",encoding="utf-8"),indent=2)
parse=lambda d:{tuple(map(int,k.split(","))):v for k,v in d.items()}
def tl_near(objs,c): return any(objs.get((c[0]+dx,c[1]+dy),{}).get("path") in TL_STOP|BLOCK for dx,dy in DIRS if(c[0]+dx,c[1]+dy)!=c)
def step(cars,objs,anim,routes):
    global TICK; TICK+=1; pos=set(cars); done=True
    for k,st in anim.items():
        rt=routes[k]
        if st["i"]>=len(rt): continue
        done=False; cur=tuple(st["pos"]); nxt=tuple(rt[st["i"]])
        if tl_near(objs,cur) or objs.get(nxt,{}).get("base")==IMG2 or nxt in pos: continue
        car=cars.pop(cur,None)
        if car:
            d=(nxt[0]-cur[0],nxt[1]-cur[1]); car.update({"path":DIR_IMG.get(d,car["path"]),"dir":d})
            cars[nxt]=car; pos.discard(cur); pos.add(nxt)
            if objs.get(nxt,{}).get("base")==IMG5: db_tl(f"{nxt[0]},{nxt[1]}","n")
            if nxt[0] in(0,COLS-1) or nxt[1] in(0,ROWS-1): db_exit(id(car))
        st["pos"]=list(nxt); st["i"]+=1
    return done

class Grid(QWidget):
    def __init__(self,side):
        super().__init__(); self.setFixedSize(COLS*CELL,ROWS*CELL); self.setMouseTracking(True)
        self.side=side; self.roads,self.objs,self.cars={},{},{}
        self.mode=self.sel=None; self._rcar=None; self._rpts=[]; self._built={}
        self._anim={}; self._tanim={}; self._troutes={}; self._tqueue=[]; self._tcar={}
        self._T={"cy":QTimer(interval=400,timeout=lambda:self._tick(self._anim,ROUTES)),
                 "tm":QTimer(interval=400,timeout=lambda:self._tick(self._tanim,self._troutes)),
                 "ts":QTimer(interval=7000,timeout=self._tmpl_spawn),
                 "rs":QTimer(timeout=self._rand_spawn),"rm":QTimer(interval=400,timeout=self._rand_move),
                 "tr":QTimer(interval=400,timeout=self._transport_tick)}
        self._tip=QLabel(self); self._tip.setStyleSheet("background:#555;color:#fff;padding:2px 4px;border-radius:3px;"); self._tip.hide()

    def mouseMoveEvent(self,e):
        x,y=int(e.position().x()//CELL),int(e.position().y()//CELL)
        if 0<=x<COLS and 0<=y<ROWS: self._tip.setText(f"x:{x} y:{y}"); self._tip.adjustSize(); self._tip.move(int(e.position().x())+10,int(e.position().y())+14); self._tip.show()
        else: self._tip.hide()
    def leaveEvent(self,_): self._tip.hide()

    def paintEvent(self,_):
        p=QPainter(self); p.fillRect(self.rect(),QColor(235,235,235))
        for layer in(self.roads,self.objs,self.cars):
            for(x,y),o in layer.items():
                img=get_px(o["path"],o.get("rot",0))
                if not img.isNull(): p.drawPixmap(x*CELL,y*CELL,CELL,CELL,img)
        if self._rcar:
            p.setPen(QPen(QColor(255,140,0,180),2))
            for x,y in self._rpts: p.drawRect(x*CELL+1,y*CELL+1,CELL-2,CELL-2)
        p.setPen(QPen(QColor(0,0,0,50)))
        for i in range(COLS+1): p.drawLine(i*CELL,0,i*CELL,ROWS*CELL)
        for i in range(ROWS+1): p.drawLine(0,i*CELL,COLS*CELL,i*CELL)

    def mousePressEvent(self,e):
        if e.button()!=Qt.MouseButton.LeftButton: return
        x,y=int(e.position().x()//CELL),int(e.position().y()//CELL)
        if not(0<=x<COLS and 0<=y<ROWS): return
        c=(x,y)
        if self.mode=='route':
            if c in self.cars:
                if self._rcar and len(self._rpts)>1: self._built[self._rcar]=list(self._rpts)
                self._rcar=c; self._rpts=[c]
            elif self._rcar and c in self.roads and c not in self._rpts: self._rpts.append(c)
            self.update(); return
        if self.mode=='place' and self.sel:
            if c in self.roads or self.sel in FREE: (self.cars if self.sel==IMG1 else self.objs)[c]=new_obj(self.sel)
        else:
            o=self.objs.get(c) or self.cars.get(c)
            if o: self.side.show_props(c,o,self)
        self.update()

    def save_route(self):
        if self._rcar and len(self._rpts)>1: self._built[self._rcar]=list(self._rpts)
        if not self._built: self._rcar=None; self._rpts=[]; return
        dlg=QDialog(); dlg.setWindowTitle("Сохранить в:"); vb=QVBoxLayout(dlg)
        def to_cycle(): ROUTES.update(self._built); self._built={}; dlg.accept()
        def to_tmpl():
            data=load_j(TMPL_FILE)
            for k,rt in self._built.items(): data[f"{k[0]},{k[1]}"]={"route":rt,"car":self.cars.get(k,new_obj(IMG1))}
            save_j(TMPL_FILE,data); self._built={}; dlg.accept()
        for lbl,fn in[("Старт/Стоп цикла",to_cycle),("Тест шаблон",to_tmpl)]:
            b=QPushButton(lbl); b.clicked.connect(fn); vb.addWidget(b)
        dlg.exec(); self._rcar=None; self._rpts=[]; self.update()

    def cancel_route(self): self._rcar=None; self._rpts=[]; self._built={}; self.update()
    def _tick(self,anim,routes):
        if step(self.cars,self.objs,anim,routes): [self._T[k].stop() for k in("cy","tm")]
        self.update()
    def start_cycle(self):
        global TICK,TL_STATS,CAR_STATS; TICK=0; TL_STATS={}; CAR_STATS={}; init_db(reset=True)
        self._anim={k:{"pos":list(k),"i":1} for k,r in ROUTES.items() if k in self.cars and len(r)>1}
        for car in self.cars.values(): db_spawn(id(car))
        if self._anim: self._T["cy"].start()
    def stop_cycle(self): self._T["cy"].stop(); db_flush(); self._anim={}; self.update()
    def start_tmpl(self):
        data=load_j(TMPL_FILE)
        if not data: return
        self._troutes={}; self._tqueue=[]; self._tanim={}; self._tcar={}
        for ks,v in data.items():
            k=tuple(map(int,ks.split(","))); self._troutes[k]=[tuple(p) for p in v["route"]]
            self._tcar[k]=dict(v.get("car",new_obj(IMG1))); self._tqueue.append(k)
        self._tmpl_spawn(); self._T["ts"].start(); self._T["tm"].start()
    def stop_tmpl(self):
        [self._T[k].stop() for k in("ts","tm")]; db_flush()
        for st in self._tanim.values(): self.cars.pop(tuple(st["pos"]),None)
        self._tanim={}; self.update()
    def _tmpl_spawn(self):
        if not self._tqueue: self._T["ts"].stop(); return
        k=self._tqueue.pop(0)
        if k in self._troutes: self.cars[k]=self._tcar[k]; db_spawn(id(self._tcar[k])); self._tanim[k]={"pos":list(k),"i":1}
        self.update()
    def start_rand(self): self._T["rs"].setInterval(random.randint(2000,5000)); self._T["rs"].start(); self._T["rm"].start()
    def stop_rand(self):
        [self._T[k].stop() for k in("rs","rm")]
        for k in[k for k,v in self.cars.items() if v.get("rand")]: del self.cars[k]
        self.update()
    def _rand_spawn(self):
        entries=[c for c in self.roads if(c[0]==0 or c[1]==0 or c[0]==COLS-1 or c[1]==ROWS-1)and c not in self.cars]
        if entries:
            c=random.choice(entries); d=(1,0) if c[0]==0 else((-1,0) if c[0]==COLS-1 else((0,1) if c[1]==0 else(0,-1)))
            car=new_obj(IMG1); car.update({"rand":True,"dir":d,"path":DIR_IMG.get(d,IMG1)}); self.cars[c]=car
        self._T["rs"].setInterval(random.randint(2000,5000))
    def _rand_move(self):
        pos=set(self.cars)
        for c in list(self.cars):
            car=self.cars.get(c)
            if not car or not car.get("rand"): continue
            dx,dy=car.get("dir",(1,0)); nxt=nd=None
            for d in[(dy,-dx),(dx,dy),(-dy,dx)]:
                cand=(c[0]+d[0],c[1]+d[1])
                if cand in self.roads and cand not in pos and not tl_near(self.objs,c) and self.objs.get(cand,{}).get("base")!=IMG2:
                    nxt=cand; nd=d; break
            if nxt is None: continue
            if not(0<=nxt[0]<COLS and 0<=nxt[1]<ROWS): del self.cars[c]; pos.discard(c); continue
            car["path"]=DIR_IMG.get(nd,car["path"]); car["dir"]=nd
            self.cars[nxt]=self.cars.pop(c); pos.discard(c); pos.add(nxt)
        self.update()
    def start_transport(self):
        for o in self.objs.values():
            if o["base"]==IMG5: o["path"]=TL_R
        self._T["tr"].start(); self.update()
    def stop_transport(self):
        self._T["tr"].stop()
        for o in self.objs.values():
            if o["base"]==IMG5: o["path"]=IMG5
        self.update()
    def _transport_tick(self):
        pos=set(self.cars)
        for c,o in self.objs.items():
            if o["base"]==IMG5: o["path"]=TL_G if any((c[0]+dx,c[1]+dy) in pos for dx,dy in DIRS) else TL_R
        self.update()
    def load(self,path):
        data=load_j(path); self.roads=parse(data.get("roads",{})); self.objs=parse(data.get("objs",{}))
        self.cars={k:v for k,v in self.objs.items() if v["base"]==IMG1}
        self.objs={k:v for k,v in self.objs.items() if v["base"]!=IMG1}; self.update()

class Side(QWidget):
    def __init__(self):
        super().__init__(); self.setFixedWidth(120); self.grid=None; self.ibtns=[]
        vb=QVBoxLayout(self); vb.setContentsMargins(6,6,6,6); vb.setSpacing(4)
        self.sp=self._sec(PLACE_IMGS); self.props=QWidget(); self.pvb=QVBoxLayout(self.props)
        self.pvb.setContentsMargins(0,0,0,0); self.pvb.setSpacing(4)
        for w in(self.sp,self.props): w.hide(); vb.addWidget(w)
        vb.addStretch()
        self.tl_lbl=QLabel("Режим светофоров:\nСтандартный"); self.mode_lbl=QLabel("Текущий режим:\nСтандартный")
        for l in(self.tl_lbl,self.mode_lbl): l.setWordWrap(True); l.setStyleSheet("font-size:10px;color:#444;"); vb.addWidget(l)

    def set_mode(self,n):
        self.tl_lbl.setText(f"Режим светофоров:\n{TL_MAP.get(n,'Стандартный')}")
        self.mode_lbl.setText(f"Текущий режим:\n{'Автоматический' if n in AUTO_MODES else 'Стандартный'}")

    def _sec(self,paths):
        w=QWidget(); vb=QVBoxLayout(w); vb.setContentsMargins(0,0,0,0)
        for p in paths:
            b=QPushButton(); b.setFixedSize(100,100); b.setCheckable(True); b.setProperty("path",p)
            ic=get_px(p)
            if not ic.isNull(): b.setIcon(QIcon(ic)); b.setIconSize(QSize(88,88))
            else: b.setText(os.path.basename(p)[:8])
            b.clicked.connect(self._pick); vb.addWidget(b); self.ibtns.append(b)
        return w

    def _pick(self):
        s=self.sender()
        for b in self.ibtns:
            if b is not s: b.setChecked(False)
        if self.grid: self.grid.sel=s.property("path") if s.isChecked() else None

    def switch(self,place=False,route=False):
        for b in self.ibtns: b.setChecked(False)
        if self.grid: self.grid.sel=None; self.grid.mode='place' if place else('route' if route else None)
        if self.grid and not route: self.grid.cancel_route()
        self.props.hide(); self.sp.setVisible(place)

    def show_props(self,cell,o,g):
        while self.pvb.count():
            w=self.pvb.takeAt(0).widget()
            if w: w.deleteLater()
        self.props.show(); base=o["base"]; add=self.pvb.addWidget
        add(QLabel(f"<b>{os.path.basename(base)}</b>"))
        if base in ROT:
            b=QPushButton("Повернуть"); b.clicked.connect(lambda:(o.update(rot=(o["rot"]+90)%360),g.update())); add(b)
        if base in CYCLES:
            b=QPushButton("Изменить тип"); cy=CYCLES[base]
            def color(_,obj=o,c=cy): i=c.index(obj["path"]) if obj["path"] in c else 0; obj["path"]=c[(i+1)%len(c)]; g.update()
            b.clicked.connect(color); add(b)
        if base==IMG5:
            add(QLabel("Все светофоры:"))
            for lbl,clr in(("🟢",TL_G),("🟡",TL_Y),("🔴",TL_R)):
                b=QPushButton(lbl)
                def sa(_,c=clr,gr=g):
                    for ob in gr.objs.values():
                        if ob["base"]==IMG5: ob["path"]=c
                    if ARD: ARD.tl(c)
                    gr.update()
                b.clicked.connect(sa); add(b)
        if base==IMG2:
            lbl=QLabel(f"Скорость: {o.get('speed',0)} сек"); add(lbl)
            for txt,d in(("+1",1),("-1",-1)):
                b=QPushButton(txt)
                def spd(_,obj=o,dv=d,l=lbl): obj["speed"]=obj.get("speed",0)+dv; l.setText(f"Скорость: {obj['speed']} сек")
                b.clicked.connect(spd); add(b)
        b=QPushButton("Удалить"); b.setStyleSheet("color:red;")
        def dele(_,c=cell,gr=g): gr.objs.pop(c,None); gr.cars.pop(c,None); gr.update(); self.props.hide()
        b.clicked.connect(dele); add(b)

def show_tables():
    dlg=QDialog(); dlg.setWindowTitle("Таблицы"); vb=QVBoxLayout(dlg); con=sqlite3.connect(DB_FILE)
    for name,cols in[("Traffic_light",["Id_light","Car_count_full_run","Car_average_in_minute","Count_color_switches"]),
                     ("Cars_stats",["Car_id","Car_spawn_ticks","Car_exit_ticks"])]:
        vb.addWidget(QLabel(f"<b>{name}</b>")); rows=con.execute(f"SELECT * FROM {name}").fetchall()
        t=QTableWidget(len(rows),len(cols)); t.setHorizontalHeaderLabels(cols)
        for r,row in enumerate(rows):
            for c,val in enumerate(row): t.setItem(r,c,QTableWidgetItem(str(val)))
        t.setFixedHeight(120); vb.addWidget(t)
    con.close(); dlg.exec()

class App(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Интеллектуальная Дорожная Система")
        lp=QPixmap(LOGO)
        if not lp.isNull(): self.setWindowIcon(QIcon(lp))
        self.side=Side(); self.grid=Grid(self.side); self.side.grid=self.grid
        self._tl_idx=0; self._tl_timer=QTimer(interval=5000,timeout=self._tl_tick)
        self._diag_idx=0; self._diag_timer=QTimer(interval=1000,timeout=self._diag_tick)
        c=QWidget(); self.setCentralWidget(c)
        root=QVBoxLayout(c); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        body=QHBoxLayout(); body.setContentsMargins(0,0,0,0); body.setSpacing(0)
        body.addWidget(self.side); body.addWidget(self.grid); root.addLayout(body)
        bar1=QHBoxLayout(); bar1.setContentsMargins(6,6,6,2); bar1.setSpacing(6)
        self.bp=QPushButton("Добавить объекты"); self.bp.setCheckable(True)
        self.brt=QPushButton("Построить маршрут"); self.brt.setCheckable(True)
        self.brs=QPushButton("Сохранить маршрут")
        self.bp.toggled.connect(lambda v:(self.brt.setChecked(False),self.side.switch(place=v),self.side.set_mode("")))
        self.brt.toggled.connect(lambda v:(self.bp.setChecked(False),self.side.switch(route=v)))
        self.brs.clicked.connect(self.grid.save_route)
        for b in(self.bp,self.brt,self.brs):
            b.setFixedHeight(32); b.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed); bar1.addWidget(b)
        root.addLayout(bar1)
        bar2=QHBoxLayout(); bar2.setContentsMargins(6,2,6,6); bar2.setSpacing(6)
        self._mb={}
        for name,chk,on,off in[
            ("Диагностика",False,self._diag,lambda:None),("Восстановление",False,self._vosstanov,lambda:None),
            ("Старт/Стоп цикла",True,self.grid.start_cycle,self.grid.stop_cycle),
            ("Режим по времени",True,lambda:(setattr(self,"_tl_idx",0),self._tl_tick(),self._tl_timer.start()),
                                     lambda:(self._tl_timer.stop(),[o.update({"path":IMG5}) for o in self.grid.objs.values() if o["base"]==IMG5],self.grid.update())),
            ("Режим по транспорту",True,self.grid.start_transport,self.grid.stop_transport),
            ("Тест шаблон",True,self.grid.start_tmpl,self.grid.stop_tmpl),
            ("Тест рандом",True,self.grid.start_rand,self.grid.stop_rand),
            ("Таблицы",False,show_tables,lambda:None)]:
            b=QPushButton(name); b.setFixedHeight(32); b.setCheckable(chk)
            b.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
            b.clicked.connect(lambda _,n=name,a=on,z=off,ck=chk:(a() if(not ck or self._mb[n].isChecked()) else z(),self.side.set_mode(n if(not ck or self._mb[n].isChecked()) else "")))
            bar2.addWidget(b); self._mb[name]=b
        root.addLayout(bar2); self.adjustSize(); self.grid.load(MAP_FILE)

    def _diag(self):
        if self._diag_timer.isActive(): self._diag_timer.stop()
        else: self._diag_idx=0; self._diag_timer.start()
    def _diag_tick(self):
        clr=[TL_R,TL_Y,TL_G][self._diag_idx%3]
        for o in self.grid.objs.values():
            if o["base"]==IMG5: o["path"]=clr
        if ARD: ARD.tl(clr)
        self._diag_idx+=1; self.grid.update()
    def _vosstanov(self):
        for o in self.grid.objs.values():
            if o["base"]==IMG5: o["path"]=TL_Y
        if ARD: ARD.send("Y")
        self.grid.update()
    def on_ard_btn(self,msg):
        if msg=="B1": QTimer.singleShot(0,self._diag)
        elif msg=="B2": QTimer.singleShot(0,self._vosstanov)
    def _tl_tick(self):
        state=TL_CYCLE[self._tl_idx%3]
        for c,o in self.grid.objs.items():
            if o["base"]==IMG5: o["path"]=state; db_tl(f"{c[0]},{c[1]}","sw")
        if ARD: ARD.tl(state)
        self._tl_idx+=1; self.grid.update()

if __name__=="__main__":
    init_db()
    port=input("COM-порт Arduino (Enter — пропустить): ").strip()
    app=QApplication(sys.argv); ARD=Arduino(port or None)
    w=App()
    if ARD: ARD.set_cb(w.on_ard_btn)
    w.show(); sys.exit(app.exec())
