[out:json][timeout:25];
way(480950645)->.lake;
way(37.2732339369621,127.05654640463246,37.288423063037904,127.06874799536753)["highway"~"^(footway|path|pedestrian|cycleway|steps)$"]->.walks;
(.lake;.walks;);out body geom;
node(w.walks);out body;
