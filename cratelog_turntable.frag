#version 330 core
out vec4 color;
uniform vec2 resolution;
uniform float rotation, elevation, lamp, pitch;
uniform vec2 arm_direction;
uniform vec3 keys;
uniform float clip_closed;
uniform vec4 strobe_phase;
uniform float velocity, speed_mix, power, room_light;
uniform sampler2D cover;
uniform sampler2D panel;
uniform sampler2D pending_cover;
uniform float pending_record, swap_progress, exchange_angle, exchange_radius;
uniform vec3 exchange_center;
uniform sampler2D pending_spine;
uniform vec3 eye;
float box(vec3 p,vec3 b){vec3 q=abs(p)-b;return length(max(q,0.))+min(max(q.x,max(q.y,q.z)),0.);}
float cyl(vec3 p,float r,float h){vec2 d=abs(vec2(length(p.xz),p.y))-vec2(r,h);return min(max(d.x,d.y),0.)+length(max(d,0.));}
float tube(vec3 p,vec3 a,vec3 b,float r){vec3 v=b-a;return length(p-a-v*clamp(dot(p-a,v)/dot(v,v),0.,1.))-r;}
float platter(vec3 p){
    // Exact radial cross-section distance: avoids overstepping the lower rim.
    vec2 q=vec2(length(p.xz),p.y);
    vec2 lower=vec2(1.66,-.075),upper=vec2(1.53,.075),edge=upper-lower;
    float side=length(q-lower-edge*clamp(dot(q-lower,edge)/dot(edge,edge),0.,1.));
    float bottom=length(q-vec2(clamp(q.x,0.,lower.x),lower.y));
    float top=length(q-vec2(clamp(q.x,0.,upper.x),upper.y));
    float radius=mix(lower.x,upper.x,clamp((q.y+.075)/.15,0.,1.));
    bool inside=abs(q.y)<.075 && q.x<radius;
    return min(side,min(bottom,top))*(inside?-1.:1.);
}
float strobeDot(float phase,float rowY,float size){
    vec2 cell=vec2(fract(phase)-.5,rowY-.5)/vec2(size,.30);
    float aa=max(fwidth(cell.x),.08);
    return 1.-smoothstep(1.-aa,1.+aa,dot(cell,cell));
}
vec2 pick(vec2 a,vec2 b){return a.x<b.x?a:b;}
// Scene units are 100 mm. 453 mm wide chassis; 372 mm overall depth includes rear fittings; 230 mm arm / 15 mm overhang.
const vec2 spindle=vec2(-.53,0.);
const vec2 pivotXZ=vec2(1.30,-1.128538878);
vec3 bezier(vec3 a,vec3 b,vec3 c,vec3 d,float t){float v=1.-t;return v*v*v*a+3.*v*v*t*b+3.*v*t*t*c+t*t*t*d;}
vec3 exchangeLocal(vec3 p){
    vec3 q=p-exchange_center;float angle=exchange_angle;
    q.yz=mat2(cos(angle),sin(angle),-sin(angle),cos(angle))*q.yz;
    return q;
}
vec2 scene(vec3 p){
    vec2 d=vec2(p.y+.48,0.);
    if(pending_record>.5){
        vec3 sleeve=p-vec3(-.53,.54,-2.70);
        d=pick(d,vec2(box(sleeve,vec3(1.,1.,.012)),14.));
        if(swap_progress>0.){
            vec3 disc=exchangeLocal(p);
            float radius=exchange_radius;
            float shape=max(cyl(disc.xzy,radius,.009),.028-length(disc.xy));
            if(swap_progress<.25)shape=max(shape,.47-p.x);
            d=pick(d,vec2(shape,15.));
        }
    }
    d=pick(d,vec2(box(p-vec3(0,.01,0),vec3(2.215,.16,1.715))-.05,1.));
    d=pick(d,vec2(box(p-vec3(0,.22,0),vec3(2.235,.07,1.735))-.03,2.));
    for(int x=-1;x<=1;x+=2)for(int z=-1;z<=1;z+=2)
        d=pick(d,vec2(cyl(p-vec3(float(x)*1.9,-.34,float(z)*1.30),.25,.14),1.));
    for(int hinge=-1;hinge<=1;hinge+=2)
        d=pick(d,vec2(box(p-vec3(float(hinge)*1.48,.27,-1.80),vec3(.18,.09,.06)),3.));
    vec3 q=p-vec3(spindle.x,.36,spindle.y);
    d=pick(d,vec2(platter(q),12.));
    if(swap_progress<.60)d=pick(d,vec2(cyl(p-vec3(spindle.x,.444,spindle.y),1.50,.009),4.));
    d=pick(d,vec2(tube(p,vec3(spindle.x,.465,spindle.y),vec3(spindle.x,.515,spindle.y),.025),13.));
    // Low armboard, height-adjustment ring and open gimbal, not a tall pedestal.
    vec3 g=p-vec3(pivotXZ.x,.40,pivotXZ.y);
    d=pick(d,vec2(cyl(g,.43,.08),1.));
    d=pick(d,vec2(cyl(g-vec3(0,.09,0),.28,.035),3.));
    d=pick(d,vec2(box(g-vec3(-.19,.25,0),vec3(.035,.16,.055)),5.));
    d=pick(d,vec2(box(g-vec3(.19,.25,0),vec3(.035,.16,.055)),5.));
    d=pick(d,vec2(box(g-vec3(0,.40,0),vec3(.22,.035,.055)),5.));
    d=pick(d,vec2(tube(g,vec3(-.24,.34,0),vec3(.24,.34,0),.048),3.));
    d=pick(d,vec2(cyl(g-vec3(.28,.12,.20),.10,.025),1.));
    // A fixed S arm in its own frame: only azimuth and cue-lift rotate the assembly.
    vec2 direction=arm_direction,side=vec2(direction.y,-direction.x);
    vec3 rel=p-vec3(pivotXZ.x,.74,pivotXZ.y);
    vec3 local=vec3(dot(rel.xz,side),rel.y,dot(rel.xz,direction));
    float cs=cos(elevation),sn=sin(elevation);
    local.yz=mat2(cs,sn,-sn,cs)*local.yz;
    if(length(local-vec3(.12,0,1.))<1.7){
        vec3 last=vec3(0);
        for(int i=1;i<=14;i++){
            float t=float(i)/14.;vec3 pt;
            if(t<.6)pt=bezier(vec3(0),vec3(.08,-.035,.42),vec3(.40,-.12,1.1),vec3(.30,-.16,1.40),t/.6);
            else pt=bezier(vec3(.30,-.16,1.40),vec3(.26,-.18,1.65),vec3(.20,-.19,1.80),vec3(.121,-.19,2.0),(t-.6)/.4);
            d=pick(d,vec2(tube(local,last,pt,.045),5.));last=pt;
        }
    }
    // Flat-ended counterweight and dial on a straight coaxial rear shaft.
    // Adjustment position is representative; the manual gives no fixed distance.
    d=pick(d,vec2(cyl((local-vec3(0,0,-.57)).xzy,.185,.135),3.));
    d=pick(d,vec2(cyl((local-vec3(0,0,-.412)).xzy,.19,.023),1.));
    d=pick(d,vec2(cyl((local-vec3(0,0,-.765)).xzy,.036,.045),5.));
    d=pick(d,vec2(tube(local,vec3(0,0,.02),vec3(0,0,-.81),.032),5.));
    // Fixed 22 degree cartridge offset, with bayonet, slotted headshell and cartridge.
    vec2 forward=vec2(-.3746066,.9271839),right=vec2(forward.y,-forward.x);
    vec3 hr=local-vec3(0,-.19,2.30);
    vec3 head=vec3(dot(hr.xz,right),hr.y,dot(hr.xz,forward));
    d=pick(d,vec2(tube(head,vec3(0,0,-.34),vec3(0,0,-.23),.046),3.));
    float shell=box(head-vec3(0,0,-.12),vec3(.095,.018,.17));
    shell=max(shell,-box(head-vec3(-.045,0,-.10),vec3(.012,.04,.065)));
    shell=max(shell,-box(head-vec3(.045,0,-.10),vec3(.012,.04,.065)));
    d=pick(d,vec2(shell,1.));
    d=pick(d,vec2(box(head-vec3(0,-.047,-.06),vec3(.063,.035,.095)),7.));
    d=pick(d,vec2(tube(head,vec3(0,-.066,-.07),vec3(0,-.085,0),.006),5.));
    d=pick(d,vec2(tube(head,vec3(0,-.085,0),vec3(0,-.09,0),.004),5.));
    d=pick(d,vec2(tube(head,vec3(.08,0,-.17),vec3(.18,.10,-.10),.012),1.));
    for(int i=-1;i<=1;i+=2)d=pick(d,vec2(cyl(head-vec3(float(i)*.045,.025,-.10),.017,.012),5.));
    // Fixed U-shaped rest: centered beneath the parked S tube, not beside it.
    vec3 rest=p-vec3(1.357550,0.620088,-0.012552);
    d=pick(d,vec2(cyl(p-vec3(1.357550,.335,-0.012552),.060,.015),1.));
    d=pick(d,vec2(tube(p,vec3(1.357550,.34,-0.012552),vec3(1.357550,0.585088,-0.012552),.027),1.));
    d=pick(d,vec2(box(rest-vec3(0,-.016,0),vec3(.068,.016,.035)),1.));
    for(int jaw=-1;jaw<=1;jaw+=2)
        d=pick(d,vec2(box(rest-vec3(float(jaw)*.061,.012,0),vec3(.012,.012,.035))-.006,1.));
    // Right-side hinge rotates a retaining arch over the seated tube.
    vec3 hinge=vec3(.077,.018,0);
    d=pick(d,vec2(tube(rest,hinge-vec3(0,0,.043),hinge+vec3(0,0,.043),.017),3.));
    vec3 latch=rest-hinge;
    float angle=(1.-clip_closed)*-1.9;
    latch.xy=mat2(cos(angle),-sin(angle),sin(angle),cos(angle))*latch.xy;
    d=pick(d,vec2(tube(latch,vec3(0),vec3(0,.112,0),.012),1.));
    d=pick(d,vec2(tube(latch,vec3(0,.112,0),vec3(-.145,.112,0),.012),1.));
    d=pick(d,vec2(tube(latch,vec3(-.145,.112,0),vec3(-.145,.052,0),.012),1.));
    d=pick(d,vec2(tube(p,vec3(1.63,.51,-0.897596),vec3(1.78,.60,-0.677596),.018),5.));
    // Keep speed keys beyond the platter's outer rim.
    d=pick(d,vec2(box(p-vec3(-1.91,.332-.008*keys.x,1.43),vec3(.20,.022,.20))-.015,3.));
    d=pick(d,vec2(box(p-vec3(-1.43,.322-.006*keys.y,1.61),vec3(.105,.009,.035)),3.));
    d=pick(d,vec2(box(p-vec3(-1.16,.322-.006*keys.z,1.61),vec3(.105,.009,.035)),3.));
    d=pick(d,vec2(box(p-vec3(-1.43,.334-.006*keys.y,1.61),vec3(.045,.004,.012)),10.));
    d=pick(d,vec2(box(p-vec3(-1.16,.334-.006*keys.z,1.61),vec3(.045,.004,.012)),11.));
    d=pick(d,vec2(cyl(p-vec3(-2.03,.40,.94),.11,.10),5.));
    d=pick(d,vec2(cyl(p-vec3(-2.03,.51,.94),.113,.018),1.));
    d=pick(d,vec2(box(p-vec3(-1.925,.44,.94),vec3(.018,.027,.055)),8.));
    // Retractable lamp: blue aperture faces inward, its top remains metal.
    d=pick(d,vec2(cyl(p-vec3(.48,.31,1.54),.055,.025),3.));
    d=pick(d,vec2(cyl(p-vec3(.48,.32+lamp*.12,1.54),.038,.025+lamp*.12),5.));
    d=pick(d,vec2(box(p-vec3(.465,.33+lamp*.22,1.505),vec3(.015,.014,.006)),6.));
    d=pick(d,vec2(cyl(p-vec3(.64,.32,1.59),.035,.012),3.));
    d=pick(d,vec2(box(p-vec3(1.93,.315,.52),vec3(.032,.006,.60)),1.));
    d=pick(d,vec2(box(p-vec3(1.93,.36,.52+pitch*.55),vec3(.12,.035,.05)),3.));
    d=pick(d,vec2(box(p-vec3(1.74,.32,.52),vec3(.028,.008,.012)),9.));
    d=pick(d,vec2(cyl(p-vec3(1.93,.33,1.29),.045,.015),3.));
    return d;
}
vec3 normal(vec3 p){vec2 e=vec2(.0015,0);return normalize(vec3(scene(p+e.xyy).x-scene(p-e.xyy).x,scene(p+e.yxy).x-scene(p-e.yxy).x,scene(p+e.yyx).x-scene(p-e.yyx).x));}
float shadow(vec3 p,vec3 l){float v=1.,t=.03;for(int i=0;i<28;i++){float h=scene(p+l*t).x;v=min(v,12.*h/t);t+=clamp(h,.025,.35);if(t>5.||v<.02)break;}return clamp(v,.12,1.);}
// World +X is right, -Z is rear: a softbox above the rear-right corner.
const vec3 keyLight=vec3(4.5,6.,-5.5);
float smithLambda(vec3 w,vec3 n,vec3 tangent,vec3 radial,vec2 alpha){
    float nw=max(dot(n,w),.0001);
    vec2 slope=alpha*vec2(dot(tangent,w),dot(radial,w))/nw;
    return .5*(sqrt(1.+dot(slope,slope))-1.);
}
float grooveBRDF(vec3 n,vec3 tangent,vec3 radial,vec3 l,vec3 v,vec2 alpha){
    float nl=dot(n,l),nv=dot(n,v);
    if(nl<=0. || nv<=0.)return 0.;
    vec3 h=normalize(l+v);
    vec3 hn=vec3(dot(h,tangent)/alpha.x,dot(h,radial)/alpha.y,dot(h,n));
    float den=dot(hn,hn);
    float distribution=1./(3.14159265*alpha.x*alpha.y*den*den);
    float masking=1./(1.+smithLambda(l,n,tangent,radial,alpha)+smithLambda(v,n,tangent,radial,alpha));
    float fresnel=.04+.96*pow(1.-max(dot(v,h),0.),5.);
    // BRDF multiplied by N.L; alpha.x is along grooves, alpha.y across them.
    return distribution*masking*fresnel/(4.*max(nv,.0001));
}
float vinylReflection(vec3 p,vec3 n,vec3 v){
    vec2 q=p.xz-spindle;float r=length(q);
    vec2 er=q/max(r,.0001),et=vec2(-er.y,er.x);
    const float groovePitch=.0012; // 0.12 mm, represented statistically when unresolved.
    float phase=r/groovePitch-(atan(q.y,q.x)-rotation)/6.2831853;
    float resolved=1.-smoothstep(.25,.9,fwidth(phase));
    float groove=cos(phase*6.2831853)*resolved;
    vec2 spiral=normalize(et+er*(groovePitch/(6.2831853*r)));
    vec3 tangent=vec3(spiral.x,0.,spiral.y),radial=normalize(cross(tangent,n));
    vec2 alpha=vec2(.026,.30*(1.+.055*sin(r*240.)+.025*groove));
    float reflected=0.;
    for(int i=0;i<4;i++){
        vec3 sampleLight=keyLight+vec3((i%2==0?-.55:.55),0.,(i<2?-.45:.45));
        reflected+=grooveBRDF(n,tangent,radial,normalize(sampleLight-p),v,alpha);
    }
    return reflected*.25;
}
void main(){
    vec3 target=vec3(0,.15,0),fw=normalize(target-eye),rt=normalize(cross(fw,vec3(0,1,0))),up=cross(rt,fw);
    vec2 uv=(gl_FragCoord.xy-.5*resolution)/min(resolution.y,resolution.x/1.5);
    vec3 rd=normalize(fw*2.5+rt*uv.x+up*uv.y);
    float t=0.;vec2 hit=vec2(0);vec3 p;bool found=false;
    for(int i=0;i<220;i++){
        p=eye+rd*t;hit=scene(p);
        if(hit.x<.0006){found=true;break;}
        if(t>28.)break;
        t+=hit.x*.85;
    }
    vec3 col=mix(vec3(.0007,.001,.0018),vec3(.035,.043,.055),room_light);
    if(found && t<28.){
        vec3 n=normal(p),l=normalize(keyLight-p),v=-rd;
        float diff=max(dot(n,l),0.),sh=shadow(p+n*.008,l),rough=.28;
        vec3 base=vec3(.09),em=vec3(0);
        float rimDots=-1.;
        float id=hit.y>13.5?hit.y:(hit.y>12.5?5.:(hit.y>11.5?3.:hit.y));
        if(id>14.5){
            vec3 disc=exchangeLocal(p);float r=length(disc.xy);
            base=vec3(.006+.002*sin(r*1200.)*exp(-max(fwidth(r)*1200.-1.,0.)));rough=.10;
            float labelRadius=exchange_radius*.3266667;
            if(r<labelRadius){base=texture(pending_cover,disc.xy/(2.*labelRadius)+.5).rgb;rough=.65;}
        }
        else if(id>13.5){
            vec2 uv=(p.xy-vec2(-.53,.54))/2.0+.5;
            if(abs(n.z)>.5)base=texture(pending_cover,uv).rgb;
            else if(n.x<-.5)base=texture(pending_spine,vec2(1.-uv.y,clamp((p.z+2.712)/.024,0.,1.))).rgb;
            else if(n.x>.5)base=vec3(.003);
            else base=vec3(.16,.15,.14);
            rough=.65;
        }
        else if(id<.5){base=vec3(.028,.034,.043);rough=.6;}
        else if(id<1.5){base=vec3(.022,.027,.033);rough=.34;}
        else if(id<2.5){base=vec3(.50,.53,.56)*(1.+.012*sin(p.x*850.)*exp(-abs(dFdx(p.x)*850.)));rough=.25;
            if(n.y>.8){vec4 ink=texture(panel,vec2((p.x+2.265)/4.53,1.-(p.z+1.765)/3.53));base=mix(base,ink.rgb,ink.a);}}
        else if(id<3.5){base=vec3(.52,.57,.62);rough=.17;
            vec3 q=p-vec3(spindle.x,.36,spindle.y);
            if(hit.y>11.5 && hit.y<12.5 && length(q.xz)>1.50 && length(q.xz)<1.69 && abs(q.y)<.078){
                base=vec3(.025,.028,.032);rough=.26;
                if(n.y<.9){
                    float rows=clamp((.075-q.y)/.15*4.,0.,3.999);
                    int row=int(floor(rows));float count=vec4(169.,174.,180.,186.)[row];
                    float size=row==2?.34:.22;
                    float angle=atan(q.z,q.x)/6.283185;
                    float physical=strobeDot((angle-rotation/6.283185)*count,fract(rows),size);
                    // Exposure filtering prevents the monitor's frame rate from inventing
                    // a false stationary row outside the strobe's illuminated sector.
                    float travel=abs(velocity)*count/3600.;
                    float contrast=travel<.001?1.:abs(sin(3.141593*travel)/(3.141593*travel));
                    physical=mix(.18,physical,contrast);
                    vec3 lightToPoint=p-vec3(-1.925,.44,.94);
                    float sector=pow(max(dot(normalize(lightToPoint),normalize(vec3(1.,-.1,-.25))),0.),6.);
                    sector*=power*(1.-smoothstep(.35,.95,length(lightToPoint)))*smoothstep(1.,10.,abs(velocity));
                    float strobed=strobeDot(angle*count-strobe_phase[row],fract(rows),size);
                    float dots=mix(physical,strobed,sector);
                    rimDots=dots;
                    base=mix(vec3(.025,.028,.032),vec3(.64,.67,.69),dots);
                    em+=vec3(1.25,.025,.004)*strobed*sector;
                }
            }}
        else if(id<4.5){vec2 q=p.xz-spindle;float r=length(q);rough=.13;
            float frequency=1200.;float filtered=exp(-max(fwidth(r)*frequency-1.,0.));
            float grooves=.5+.5*sin(r*frequency)*filtered;base=vec3(.003+.0015*grooves+.0005*sin(r*240.));
            if(r<.49){float c=cos(rotation),s=sin(rotation);vec2 tex=mat2(c,-s,s,c)*q/.98+.5; base=texture(cover,vec2(tex.x,1.-tex.y)).rgb;rough=.65;}
            else {rough=.07;}}
        else if(id<5.5){base=vec3(.72,.77,.82);rough=.10;}
        else if(id<6.5){base=vec3(.015,.10,.22);em=vec3(.02,.22,1.1)*lamp;}
        else if(id<7.5){base=vec3(.11,.055,.025);rough=.35;}
        else if(id<8.5){base=vec3(.4,.015,.006);em=vec3(1.,.025,.003);}
        else if(id<9.5){base=vec3(.12,.5,.02);em=vec3(.1,.6,.01);}
        else {float on=id<10.5?1.-speed_mix:speed_mix;base=vec3(.035,.006,.002);em=vec3(1.,.07,.008)*on;}
        if(id>5.5 && id<6.5 || id>7.5 && id<11.5)base=mix(vec3(.012),base,power);
        em*=power;
        float spec=pow(max(dot(reflect(-l,n),v),0.),mix(150.,10.,rough));
        if(id>3.5 && id<4.5 && length(p.xz-spindle)>.49 && n.y>.8){
            spec=vinylReflection(p,n,v)*3.0;
        }
        if(hit.y>12.5 && hit.y<13.5){
            // Polished stainless spindle: neutral silver with crisp reflected lights.
            base=vec3(.78,.81,.84);
            vec3 reflection=reflect(-v,n);
            float strip=pow(max(dot(reflection,normalize(vec3(-.6,1.,.4))),0.),48.);
            float softbox=pow(max(dot(reflection,normalize(vec3(.8,.7,-.5))),0.),12.);
            em+=room_light*vec3(.90,.94,1.)*(strip*1.8+softbox*.65);
            spec=pow(max(dot(reflect(-l,n),v),0.),240.)*2.5;
        }
        float ao=clamp(scene(p+n*.12).x/.12,.35,1.);
        col=base*(mix(.003,.26*ao,room_light)+room_light*.82*diff*sh)+room_light*vec3(spec*.65*sh)+em;
        vec3 red=vec3(-1.925,.44,.94)-p;
        float redBeam=pow(max(dot(normalize(-red),normalize(vec3(1.,-.1,-.25))),0.),6.);
        float rimResponse=rimDots<0.?1.:mix(.035,1.65,rimDots);
        col+=rimResponse*power*vec3(1.,.025,.006)*max(dot(n,normalize(red)),0.)*redBeam/(1.+dot(red,red)*12.);
        vec3 glow=vec3(.465,.33+lamp*.22,1.505)-p;
        float beam=pow(max(dot(normalize(-glow),normalize(vec3(-.45,-.20,-1.))),0.),10.);
        vec3 blueLight=power*lamp*vec3(.025,.34,1.65)*mix(2.2,1.,room_light)/(1.+dot(glow,glow)*3.);
        col+=rimResponse*blueLight*max(dot(n,normalize(glow)),0.)*beam;
        // The local lamp remains reflected in polished vinyl when room lights are off.
        if(id>3.5 && id<4.5 && length(p.xz-spindle)>.49 && n.y>.8){
            vec3 halfBlue=normalize(normalize(glow)+v);
            float glossy=pow(max(dot(n,halfBlue),0.),180.);
            float sheen=pow(max(dot(n,halfBlue),0.),24.);
            float fresnel=.04+.96*pow(1.-max(dot(n,v),0.),5.);
            col+=blueLight*beam*(glossy*18.+sheen*.8)*fresnel;
        }
        col=mix(col,mix(vec3(.0005,.0007,.0012),vec3(.025,.03,.04),room_light),1.-exp(-.002*t));
    }
    col=pow(max(col,0.),vec3(1./2.2));color=vec4(col,1.);
}
