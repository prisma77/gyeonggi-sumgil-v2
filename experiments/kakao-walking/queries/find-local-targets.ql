[out:json][timeout:25];
area["boundary"="administrative"]["name"="수원시"]->.suwon;
area["boundary"="administrative"]["name"="성남시"]->.seongnam;
(
  nwr(area.suwon)["name"="원천호수"];
  nwr(area.suwon)["name:ko"="원천호수"];
  nwr(area.seongnam)["name"="탄천"]["waterway"="river"];
);
out body geom;
