{
    # use carto light for its lisibility
    provider: "carto", 
    # default zoom
    zoom: 15,
    # coordinate of first node (must have coordinates ;))
    lat: [.[]]|.[0].adv_lat,
    lon: [.[]]|.[0].adv_lon,
    markers: [
      .[]
          | select(.adv_lat != 0.0 or .adv_lon != 0.0)
          | {
          lat: .adv_lat,
          lon: .adv_lon,
          caption: (.adv_name // .public_key[0:8])
        }
    ]
}
