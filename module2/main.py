# КОД НА ЭТАПЕ РАЗРАБОТКЕ, работают все ржимы, кроме тех, котоыре затрагивают программную часть
import sys, json, os, sqlite3, random
from PyQt6.QtWidgets import *
from PyQt6.QtGui import QPainter, QColor, QPen, QIcon, QPixmap, QTransform
from PyQt6.QtCore import Qt, QSize, QTimer

M2,M=r"module2\media",r"module1\media"
MAP_FILE,TMPL_FILE,DB_FILE=r"map.json",r"template.json",r"traffic.db"
LOGO=f"{M}\\TLgreen.png"
IMG1,IMG2,IMG3,IMG4,IMG5=f"{M}\\Cbottom.png",f"{M}\\Pedestrain.png",f"{M}\\Block.png",f"{M}\\Zhorizontal.png",f"{M}\\TLyellow.png"
PLACE_IMGS=[IMG1,IMG2,IMG3,IMG4,IMG5]
FREE={IMG2,IMG3}; ROT={IMG2,IMG4}
CYCLES={IMG1:[IMG1,f"{M}\\BCvertical.png",f"{M}\\GCicon.ico"],
        IMG3:[IMG3,f"{M}\\Stop.png",f"{M}\\Start.png"],
        IMG5:[IMG5,f"{M}\\TLred.png",f"{M}\\TLgreen.png"]}
TL_CYCLE=[f"{M}\\TLred.png",f"{M}\\TLyellow.png",f"{M}\\TLgreen.png"]
TL_STOP={f"{M}\\TLred.png"}
TL_G,TL_R,TL_Y=f"{M}\\TLgreen.png",f"{M}\\TLred.png",f"{M}\\TLyellow.png"
DIR_IMG={(1,0):f"{M2}\\Cright.png",(0,1):f"{M2}\\Cbottom.png",
         (-1,0):f"{M2}\\Cleft.png",(0,-1):f"{M2}\\Cvertical.png"}
BLOCK={f"{M2}\\Block.png",f"{M2}\\Stop.png"}
DIRS=[(1,0),(-1,0),(0,1),(0,-1)]
CELL,COLS,ROWS=36,21,21
AUTO_MODES={"Старт/Стоп цикла","Режим по времени","Режим по транспорту","Тест шаблон","Тест рандом"}
TL_MAP={"Диагностика":"Сброс","Восстановление":"Восстановление","Режим по времени":"По времени",
        "Режим по транспорту":"По транспорту","Тест шаблон":"Тест шаблон","Тест рандом":"Тест рандом"}
ROUTES:dict={}  # маршруты Старт/Стоп цикла

# глобальные счётчики
TICK=0                        # тик с момента старта теста
TL_STATS={}                   # {tl_id: {"count":0,"switches":0,"start_tick":0}}
CAR_STATS={}                  # {car_id: {"spawn":tick}}

def init_db(reset=False):
    con=sqlite3.connect(DB_FILE)
    con.execute("CREATE TABLE IF NOT EXISTS Traffic_light (Id_light,Car_count_full_run,Car_average_in_minute,Count_color_switches)")
    con.execute("CREATE TABLE IF NOT EXISTS Cars_stats (Car_id,Car_spawn_ticks,Car_exit_ticks)")
    if reset:
        con.execute("DELETE FROM Traffic_light")
        con.execute("DELETE FROM Cars_stats")
    con.commit(); con.close()

def db_car_spawn(car_id):
    CAR_STATS[car_id]={"spawn":TICK}

def db_car_exit(car_id):
    if car_id not in CAR_STATS: return
    con=sqlite3.connect(DB_FILE)
    con.execute("INSERT INTO Cars_stats VALUES (?,?,?)",(car_id,CAR_STATS.pop(car_id)["spawn"],TICK))
    con.commit(); con.close()

def db_car_passed_tl(tl_id):
    TL_STATS.setdefault(tl_id,{"count":0,"switches":0,"start_tick":TICK})
    TL_STATS[tl_id]["count"]+=1

def db_tl_switch(tl_id):
    TL_STATS.setdefault(tl_id,{"count":0,"switches":0,"start_tick":TICK})
    TL_STATS[tl_id]["switches"]+=1

def db_flush_tl():
    if not TL_STATS: return
    con=sqlite3.connect(DB_FILE); rows=[]
    for tid,s in TL_STATS.items():
        elapsed_min=max((TICK-s["start_tick"])*0.4/60,0.001)
        rows.append((tid,s["count"],round(s["count"]/elapsed_min,2),s["switches"]))
    con.executemany("INSERT OR REPLACE INTO Traffic_light VALUES (?,?,?,?)",rows)
    con.commit(); con.close()

get_px=lambda path,rot=0:(lambda p:p.transformed(QTransform().rotate(rot)) if rot and not p.isNull() else p)(QPixmap(path))
new_obj=lambda path:{"path":path,"base":path,"rot":0,"speed":0}
parse_kv=lambda d:{tuple(map(int,k.split(","))):v for k,v in d.items()}

def tl_near(objs,c,skip=None):
    return any(objs.get((c[0]+dx,c[1]+dy),{}).get("path") in TL_STOP|BLOCK
               for dx,dy in((1,0),(-1,0),(0,1),(0,-1)) if (c[0]+dx,c[1]+dy)!=skip)

def step(cars,objs,anim,routes):
    global TICK; TICK+=1
    pos=set(cars); done=True
    for k,st in anim.items():
        rt=routes[k]
        if st["i"]>=len(rt): continue
        done=False; cur=tuple(st["pos"]); nxt=tuple(rt[st["i"]])
        if tl_near(objs,cur,skip=cur) or objs.get(nxt,{}).get("base")==IMG2 or nxt in pos: continue
        car=cars.pop(cur,None)
        if car:
            d=(nxt[0]-cur[0],nxt[1]-cur[1]); car["path"]=DIR_IMG.get(d,car["path"]); car["dir"]=d
            cars[nxt]=car; pos.discard(cur); pos.add(nxt)
            # проехал через светофор?
            tl=objs.get(nxt,{}); 
            if tl.get("base")==IMG5: db_car_passed_tl(f"{nxt[0]},{nxt[1]}")
            # выехал за пределы?
            if nxt[0] in(0,COLS-1) or nxt[1] in(0,ROWS-1): db_car_exit(id(car))
        st["pos"]=list(nxt); st["i"]+=1
    return done

def load_json(path, default=None):
    try:
        with open(path,encoding="utf-8") as f: return json.load(f)
    except Exception: return default or {}

def save_json(path,data):
    with open(path,"w",encoding="utf-8") as f: json.dump(data,f,indent=2)


class Grid(QWidget):
    def __init__(self,side):
        super().__init__()
        self.setFixedSize(COLS*CELL,ROWS*CELL); self.setMouseTracking(True)
        self.side=side; self.roads,self.objs,self.cars={},{},{}
        self.mode=self.sel=None
        self._rcar=None; self._rpts=[]; self._built={}  # накопленные маршруты до сохранения
        self._anim={}; self._tanim={}; self._troutes={}; self._tqueue=[]
        self._T={"cycle":QTimer(interval=400,timeout=lambda:self._tick(self._anim,ROUTES)),
                 "tmpl" :QTimer(interval=400,timeout=lambda:self._tick(self._tanim,self._troutes)),
                 "tspwn":QTimer(interval=7000,timeout=self._tmpl_spawn),
                 "rspwn":QTimer(timeout=self._rand_spawn),
                 "rmov" :QTimer(interval=400,timeout=self._rand_move),
                 "trns" :QTimer(interval=400,timeout=self._transport_tick)}
        self._tip=QLabel(self); self._tip.setStyleSheet("background:#555;color:#fff;padding:2px 4px;border-radius:3px;"); self._tip.hide()

    def mouseMoveEvent(self,e):
        x,y=int(e.position().x()//CELL),int(e.position().y()//CELL)
        if 0<=x<COLS and 0<=y<ROWS:
            self._tip.setText(f"x:{x} y:{y}"); self._tip.adjustSize()
            self._tip.move(int(e.position().x())+10,int(e.position().y())+14); self._tip.show()
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
                # сохраняем текущий в буфер, начинаем новый
                if self._rcar and len(self._rpts)>1: self._built[self._rcar]=list(self._rpts)
                self._rcar=c; self._rpts=[c]
            elif self._rcar and c in self.roads and c not in self._rpts:
                self._rpts.append(c)
            self.update(); return
        if self.mode=='place' and self.sel:
            if c in self.roads or self.sel in FREE:
                (self.cars if self.sel==IMG1 else self.objs)[c]=new_obj(self.sel)
        else:
            o=self.objs.get(c) or self.cars.get(c)
            if o: self.side.show_props(c,o,self)
        self.update()

    def save_route(self):
        # добавить текущий незафиксированный маршрут в буфер
        if self._rcar and len(self._rpts)>1: self._built[self._rcar]=list(self._rpts)
        if not self._built: self._rcar=None; self._rpts=[]; return
        dlg=QDialog(); dlg.setWindowTitle("Сохранить в:"); vb=QVBoxLayout(dlg)
        def to_cycle():
            ROUTES.update(self._built); self._built={}; dlg.accept()
        def to_tmpl():
            data=load_json(TMPL_FILE)   # читаем существующий файл
            for k,rt in self._built.items():
                data[f"{k[0]},{k[1]}"]={"route":rt,"car":self.cars.get(k,new_obj(IMG1))}
            save_json(TMPL_FILE,data); self._built={}; dlg.accept()
        for lbl,fn in[("Старт/Стоп цикла",to_cycle),("Тест шаблон",to_tmpl)]:
            b=QPushButton(lbl); b.clicked.connect(fn); vb.addWidget(b)
        dlg.exec()
        self._rcar=None; self._rpts=[]; self.update()

    def cancel_route(self): self._rcar=None; self._rpts=[]; self._built={}; self.update()

    # ── общий тик движения ───────────────────────────────────────────────
    def _tick(self,anim,routes):
        if step(self.cars,self.objs,anim,routes): self.sender().stop()
        self.update()

    # ── Старт/Стоп цикла ────────────────────────────────────────────────
    def start_cycle(self):
        global TICK,TL_STATS,CAR_STATS; TICK=0; TL_STATS={}; CAR_STATS={}
        init_db(reset=True)
        self._anim={k:{"pos":list(k),"i":1} for k,r in ROUTES.items() if k in self.cars and len(r)>1}
        for car in self.cars.values(): db_car_spawn(id(car))
        if self._anim: self._T["cycle"].start()

    def stop_cycle(self):
        self._T["cycle"].stop(); db_flush_tl(); self._anim={}; self.update()

    # ── Тест шаблон ─────────────────────────────────────────────────────
    def start_tmpl(self):
        data=load_json(TMPL_FILE)
        if not data: return
        self._troutes={}; self._tqueue=[]; self._tanim={}; self._tcar={}
        for ks,v in data.items():
            k=tuple(map(int,ks.split(",")))
            self._troutes[k]=[tuple(p) for p in v["route"]]
            self._tcar[k]=dict(v.get("car",new_obj(IMG1)))  # храним отдельно
            self._tqueue.append(k)
        self._tmpl_spawn(); self._T["tspwn"].start(); self._T["tmpl"].start()

    def stop_tmpl(self):
        self._T["tspwn"].stop(); self._T["tmpl"].stop(); db_flush_tl()
        for st in self._tanim.values(): self.cars.pop(tuple(st["pos"]),None)
        self._tanim={}; self.update()

    def _tmpl_spawn(self):
        if not self._tqueue: self._T["tspwn"].stop(); return
        k=self._tqueue.pop(0)
        if k in self._troutes:
            self.cars[k]=self._tcar[k]; db_car_spawn(id(self._tcar[k]))
            self._tanim[k]={"pos":list(k),"i":1}
        self.update()

    # ── Тест рандом ─────────────────────────────────────────────────────
    def start_rand(self):
        self._T["rspwn"].setInterval(random.randint(2000,5000)); self._T["rspwn"].start(); self._T["rmov"].start()

    def stop_rand(self):
        self._T["rspwn"].stop(); self._T["rmov"].stop()
        for k in[k for k,v in self.cars.items() if v.get("rand")]: del self.cars[k]
        self.update()

    def _rand_spawn(self):
        entries=[c for c in self.roads if(c[0]==0 or c[1]==0 or c[0]==COLS-1 or c[1]==ROWS-1)and c not in self.cars]
        if entries:
            c=random.choice(entries)
            d=(1,0) if c[0]==0 else((-1,0) if c[0]==COLS-1 else((0,1) if c[1]==0 else(0,-1)))
            car=new_obj(IMG1); car.update({"rand":True,"dir":d,"path":DIR_IMG.get(d,IMG1)}); self.cars[c]=car
        self._T["rspwn"].setInterval(random.randint(2000,5000))

    def _rand_move(self):
        pos=set(self.cars)
        for c in list(self.cars):
            car=self.cars.get(c)
            if not car or not car.get("rand"): continue
            dx,dy=car.get("dir",(1,0))
            nxt=nd=None
            for d in[(dy,-dx),(dx,dy),(-dy,dx)]:
                cand=(c[0]+d[0],c[1]+d[1])
                if cand in self.roads and cand not in pos and not tl_near(self.objs,c,skip=c) and self.objs.get(cand,{}).get("base")!=IMG2:
                    nxt=cand; nd=d; break
            if nxt is None: continue
            if not(0<=nxt[0]<COLS and 0<=nxt[1]<ROWS): del self.cars[c]; pos.discard(c); continue
            car["path"]=DIR_IMG.get(nd,car["path"]); car["dir"]=nd
            self.cars[nxt]=self.cars.pop(c); pos.discard(c); pos.add(nxt)
        self.update()

    # ── Режим по транспорту ──────────────────────────────────────────────
    def start_transport(self):
        for o in self.objs.values():
            if o["base"]==IMG5: o["path"]=TL_R
        self._T["trns"].start(); self.update()

    def stop_transport(self):
        self._T["trns"].stop()
        for o in self.objs.values():
            if o["base"]==IMG5: o["path"]=IMG5
        self.update()

    def _transport_tick(self):
        pos=set(self.cars)
        for c,o in self.objs.items():
            if o["base"]==IMG5:
                o["path"]=TL_G if any((c[0]+dx,c[1]+dy) in pos for dx,dy in DIRS) else TL_R
        self.update()

    def load(self,path):
        try:
            data=load_json(path)
            self.roads=parse_kv(data.get("roads",{})); self.objs=parse_kv(data.get("objs",{}))
            self.cars={k:v for k,v in self.objs.items() if v["base"]==IMG1}
            self.objs={k:v for k,v in self.objs.items() if v["base"]!=IMG1}
            self.update()
        except Exception: pass


class Side(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(120); self.grid=None; self.ibtns=[]
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
        if self.grid:
            self.grid.sel=None; self.grid.mode='place' if place else('route' if route else None)
            if not route: self.grid.cancel_route()
        self.props.hide(); self.sp.setVisible(place)

    def show_props(self,cell,o,grid):
        while self.pvb.count():
            w=self.pvb.takeAt(0).widget()
            if w: w.deleteLater()
        self.props.show(); base=o["base"]
        self.pvb.addWidget(QLabel(f"<b>{os.path.basename(base)}</b>"))
        if base in ROT:
            b=QPushButton("Повернуть"); b.clicked.connect(lambda:(o.update(rot=(o["rot"]+90)%360),grid.update())); self.pvb.addWidget(b)
        if base in CYCLES:
            b=QPushButton("Изменить тип"); cy=CYCLES[base]
            def color(_,obj=o,c=cy): i=c.index(obj["path"]) if obj["path"] in c else 0; obj["path"]=c[(i+1)%len(c)]; grid.update()
            b.clicked.connect(color); self.pvb.addWidget(b)
        if base==IMG5:
            self.pvb.addWidget(QLabel("Все светофоры:"))
            for lbl,clr in(("🟢",TL_G),("🟡",TL_Y),("🔴",TL_R)):
                b=QPushButton(lbl)
                def sa(_,c=clr,g=grid):
                    for ob in g.objs.values():
                        if ob["base"]==IMG5: ob["path"]=c
                    g.update()
                b.clicked.connect(sa); self.pvb.addWidget(b)
        if base==IMG2:
            lbl=QLabel(f"Скорость: {o.get('speed',0)} сек"); self.pvb.addWidget(lbl)
            for txt,d in(("+1",1),("-1",-1)):
                b=QPushButton(txt)
                def spd(_,obj=o,dv=d,l=lbl): obj["speed"]=obj.get("speed",0)+dv; l.setText(f"Скорость: {obj['speed']} сек")
                b.clicked.connect(spd); self.pvb.addWidget(b)
        b=QPushButton("Удалить"); b.setStyleSheet("color:red;")
        def dele(_,c=cell,g=grid): g.objs.pop(c,None); g.cars.pop(c,None); g.update(); self.props.hide()
        b.clicked.connect(dele); self.pvb.addWidget(b)


def show_tables():
    dlg=QDialog(); dlg.setWindowTitle("Таблицы"); vb=QVBoxLayout(dlg); con=sqlite3.connect(DB_FILE)
    for name,cols in[("Traffic_light",["Id_light","Car_count_full_run","Car_average_in_minute","Count_color_switches"]),
                     ("Cars_stats",["Car_id","Car_spawn_ticks","Car_exit_ticks"])]:
        vb.addWidget(QLabel(f"<b>{name}</b>"))
        rows=con.execute(f"SELECT * FROM {name}").fetchall()
        t=QTableWidget(len(rows),len(cols)); t.setHorizontalHeaderLabels(cols)
        for r,row in enumerate(rows):
            for c,val in enumerate(row): t.setItem(r,c,QTableWidgetItem(str(val)))
        t.setFixedHeight(120); vb.addWidget(t)
    con.close(); dlg.exec()


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Интеллектуальная Дорожная Система")
        lp=QPixmap(LOGO)
        if not lp.isNull(): self.setWindowIcon(QIcon(lp))
        self.side=Side(); self.grid=Grid(self.side); self.side.grid=self.grid
        self._tl_idx=0; self._tl_timer=QTimer(interval=5000,timeout=self._tl_tick)
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
            ("Диагностика",False,lambda:None,lambda:None),
            ("Восстановление",False,lambda:None,lambda:None),
            ("Старт/Стоп цикла",True,self.grid.start_cycle,self.grid.stop_cycle),
            ("Режим по времени",True,lambda:(setattr(self,"_tl_idx",0),self._tl_tick(),self._tl_timer.start()),
                                     lambda:(self._tl_timer.stop(),[o.update({"path":IMG5}) for o in self.grid.objs.values() if o["base"]==IMG5],self.grid.update())),
            ("Режим по транспорту",True,self.grid.start_transport,self.grid.stop_transport),
            ("Тест шаблон",True,self.grid.start_tmpl,self.grid.stop_tmpl),
            ("Тест рандом",True,self.grid.start_rand,self.grid.stop_rand),
            ("Таблицы",False,show_tables,lambda:None),
        ]:
            b=QPushButton(name); b.setFixedHeight(32); b.setCheckable(chk)
            b.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
            b.clicked.connect(lambda _,n=name,a=on,z=off,c=chk:(a() if (not c or self._mb[n].isChecked()) else z(),self.side.set_mode(n if (not c or self._mb[n].isChecked()) else "")))
            bar2.addWidget(b); self._mb[name]=b
        root.addLayout(bar2); self.adjustSize(); self.grid.load(MAP_FILE)

    def _tl_tick(self):
        state=TL_CYCLE[self._tl_idx%3]
        for c,o in self.grid.objs.items():
            if o["base"]==IMG5: o["path"]=state; db_tl_switch(f"{c[0]},{c[1]}")
        self._tl_idx+=1; self.grid.update()

if __name__=="__main__":
    init_db(reset=False); app=QApplication(sys.argv); App().show(); sys.exit(app.exec())
