/**
 * Shared GLSL chunks for the procedural gold look.
 *
 * Everything is analytic: no HDR files or textures are downloaded. The
 * "studio" environment is a handful of soft area lights expressed as
 * functions of the reflection vector, which is what gives the metal its
 * crisp, expensive highlights.
 */

/** 3D simplex noise (Ashima Arts / Stefan Gustavson, MIT). */
export const NOISE = /* glsl */ `
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0);
  const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy));
  vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz);
  vec3 l=1.0-g;
  vec3 i1=min(g.xyz,l.zxy);
  vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx;
  vec3 x2=x0-i2+C.yyy;
  vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(
    i.z+vec4(0.0,i1.z,i2.z,1.0))
    +i.y+vec4(0.0,i1.y,i2.y,1.0))
    +i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857;
  vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z);
  vec4 x_=floor(j*ns.z);
  vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy;
  vec4 y=y_*ns.x+ns.yyyy;
  vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy);
  vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0;
  vec4 s1=floor(b1)*2.0+1.0;
  vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;
  vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x);
  vec3 p1=vec3(a0.zw,h.y);
  vec3 p2=vec3(a1.xy,h.z);
  vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0);
  m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}
`;

/**
 * Procedural warm studio environment + physically-inspired gold BRDF.
 * Output is linear HDR; tone mapping happens in the output pass.
 */
export const GOLD = /* glsl */ `
float softBox(vec3 d, vec3 axis, float size, float sharp){
  float c = dot(d, normalize(axis));
  return smoothstep(1.0 - size, 1.0 - size + sharp, c);
}

vec3 studioEnv(vec3 d){
  float y = d.y;
  // dark obsidian dome with a warm horizon
  vec3 col = mix(vec3(0.010,0.006,0.003), vec3(0.050,0.032,0.014), smoothstep(-0.4,0.8,y));
  col += vec3(0.55,0.28,0.07) * 0.55 * exp(-pow(y*5.0,2.0));
  // large overhead softbox
  col += vec3(1.00,0.88,0.66) * 1.5 * smoothstep(0.66,0.95,y);
  // key light, upper right
  col += vec3(1.00,0.84,0.58) * 4.2 * softBox(d, vec3(0.75,0.45,0.55), 0.06, 0.035);
  // long vertical strip on the left, gives the liquid its sharp rim
  float strip = exp(-pow((d.x + 0.72)*9.0, 2.0)) * smoothstep(-0.5,0.3,y) * step(0.0, d.z + 0.6);
  col += vec3(1.00,0.80,0.50) * 2.4 * strip;
  // warm back fill
  col += vec3(0.95,0.55,0.18) * 1.4 * softBox(d, vec3(-0.3,0.15,-1.0), 0.18, 0.12);
  // floor bounce from the glowing platform
  col += vec3(0.75,0.40,0.10) * 0.7 * smoothstep(-0.15,-0.85,y);
  return col;
}

vec3 goldF0(){ return vec3(1.000, 0.766, 0.336); }

vec3 shadeGold(vec3 N, vec3 V, float rough, vec3 tint){
  vec3 R = reflect(-V, N);
  float NdV = clamp(dot(N, V), 0.0, 1.0);
  vec3 F0 = goldF0() * tint;
  vec3 F = F0 + (vec3(1.0) - F0) * pow(1.0 - NdV, 5.0);
  // cheap roughness: blend the sharp reflection with a broad, normal-oriented lobe
  vec3 sharp = studioEnv(R);
  vec3 broad = studioEnv(normalize(mix(R, N, 0.65))) * 0.55;
  vec3 spec = mix(sharp, broad, rough) * F;
  // subtle deep-bronze body so grazing shadows never go to pure black
  spec += vec3(0.060,0.028,0.006) * (1.0 - NdV);
  return spec;
}
`;
