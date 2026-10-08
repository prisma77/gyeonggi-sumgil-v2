[out:json][timeout:25];
way(480950645)->.lake;
(
  way(around.lake:300)["highway"~"^(footway|path|pedestrian|cycleway|steps)$"];
  way(around.lake:300)["highway"~"^(service|residential|living_street)$"]["foot"~"^(yes|designated|permissive)$"];
)->.walks;
(.lake;.walks;);out body geom;
node(w.walks);out body;
