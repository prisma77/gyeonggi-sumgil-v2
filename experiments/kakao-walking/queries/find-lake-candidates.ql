[out:json][timeout:25];
area["boundary"="administrative"]["name"="수원시"]->.suwon;
(
  area.suwon;
  nwr(area.suwon)["name"~"원천|광교"];
  nwr(area.suwon)["natural"="water"];
);
out body geom;
