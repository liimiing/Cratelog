// Direct Cocoa presentation. All entry points run on Tk's main thread.
#import <Cocoa/Cocoa.h>
#import <OpenGL/gl3.h>
#import <CoreText/CoreText.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifndef CRATELOG_TURNTABLE_HASH
#define CRATELOG_TURNTABLE_HASH "untracked"
#endif
const char *cratelog_turntable_hash(void){return CRATELOG_TURNTABLE_HASH;}
@interface CratelogTurntableView:NSOpenGLView {
@public GLuint sceneProgram,overlayProgram,vao,vbo,textures[5],fbo,colorTexture;
int renderWidth,renderHeight; BOOL ready; char lastError[1024];
}
@end
@implementation CratelogTurntableView
- (BOOL)isOpaque{return YES;}
- (NSView *)hitTest:(NSPoint)p{return nil;}
- (void)viewDidMoveToWindow{
    [super viewDidMoveToWindow];
    if(self.window){[self.openGLContext setView:self];[self.openGLContext update];}
}
- (void)reshape{[super reshape];[self.openGLContext update];}
- (void)viewDidChangeBackingProperties{
    [super viewDidChangeBackingProperties];[self.openGLContext update];
}
@end
static GLuint program(const char *fragment,char *error,size_t capacity){
    const char *vertex="#version 330 core\nlayout(location=0) in vec2 position;void main(){gl_Position=vec4(position,0,1);}";
    GLuint shaders[2]={glCreateShader(GL_VERTEX_SHADER),glCreateShader(GL_FRAGMENT_SHADER)};
    const char *sources[2]={vertex,fragment};GLint ok=0;
    for(int i=0;i<2;i++){
        glShaderSource(shaders[i],1,&sources[i],NULL);glCompileShader(shaders[i]);
        glGetShaderiv(shaders[i],GL_COMPILE_STATUS,&ok);
        if(!ok){glGetShaderInfoLog(shaders[i],(GLsizei)capacity,NULL,error);glDeleteShader(shaders[0]);glDeleteShader(shaders[1]);return 0;}
    }
    GLuint p=glCreateProgram();glAttachShader(p,shaders[0]);glAttachShader(p,shaders[1]);glLinkProgram(p);
    glDeleteShader(shaders[0]);glDeleteShader(shaders[1]);glGetProgramiv(p,GL_LINK_STATUS,&ok);
    if(!ok){glGetProgramInfoLog(p,(GLsizei)capacity,NULL,error);glDeleteProgram(p);return 0;}return p;
}
void cratelog_turntable_destroy(void *handle){
    if(!handle)return;
    CratelogTurntableView *v=(__bridge_transfer CratelogTurntableView *)handle;
    [v.openGLContext makeCurrentContext];
    glDeleteProgram(v->sceneProgram);glDeleteProgram(v->overlayProgram);
    glDeleteTextures(5,v->textures);glDeleteTextures(1,&v->colorTexture);glDeleteFramebuffers(1,&v->fbo);
    glDeleteBuffers(1,&v->vbo);glDeleteVertexArrays(1,&v->vao);
    [v removeFromSuperview];[v clearGLContext];
}
void *cratelog_turntable_create(void *parent,const char *source,char *error,size_t capacity){
    @autoreleasepool {
        if(!parent||![NSThread isMainThread]){snprintf(error,capacity,"Cocoa view requires main thread");return NULL;}
        NSOpenGLPixelFormatAttribute attrs[]={NSOpenGLPFAOpenGLProfile,NSOpenGLProfileVersion4_1Core,NSOpenGLPFAAccelerated,NSOpenGLPFADoubleBuffer,NSOpenGLPFAColorSize,24,0};
        NSOpenGLPixelFormat *format=[[NSOpenGLPixelFormat alloc]initWithAttributes:attrs];
        CratelogTurntableView *v=[[CratelogTurntableView alloc]initWithFrame:NSMakeRect(0,0,32,32) pixelFormat:format];
        if(!format||!v.openGLContext){snprintf(error,capacity,"OpenGL 4.1 context unavailable");return NULL;}
        void *handle=(__bridge_retained void *)v;
        v.wantsBestResolutionOpenGLSurface=YES;
        v.autoresizingMask=[(__bridge NSView *)parent isFlipped]?NSViewMaxYMargin:NSViewMinYMargin;
        [(__bridge NSView *)parent addSubview:v];
        // We render from Tk, outside NSOpenGLView's normal drawRect lifecycle.
        // Explicitly attach the window drawable before using framebuffer zero.
        [v.openGLContext setView:v];[v.openGLContext update];[v.openGLContext makeCurrentContext];
        GLint interval=0;[v.openGLContext setValues:&interval forParameter:NSOpenGLCPSwapInterval];
        v->sceneProgram=program(source,error,capacity);
        v->overlayProgram=program("#version 330 core\nout vec4 color;uniform sampler2D hud;uniform vec2 resolution;void main(){vec2 uv=gl_FragCoord.xy/resolution;color=texture(hud,vec2(uv.x,1.-uv.y));}",error,capacity);
        if(!v->sceneProgram||!v->overlayProgram){cratelog_turntable_destroy(handle);return NULL;}
        const GLfloat vertices[]={-1,-1,1,-1,1,1,-1,-1,1,1,-1,1};
        glGenVertexArrays(1,&v->vao);glBindVertexArray(v->vao);glGenBuffers(1,&v->vbo);glBindBuffer(GL_ARRAY_BUFFER,v->vbo);
        glBufferData(GL_ARRAY_BUFFER,sizeof(vertices),vertices,GL_STATIC_DRAW);glEnableVertexAttribArray(0);glVertexAttribPointer(0,2,GL_FLOAT,GL_FALSE,0,0);
        glGenTextures(5,v->textures);glGenFramebuffers(1,&v->fbo);glGenTextures(1,&v->colorTexture);
        for(int i=0;i<5;i++){
            glBindTexture(GL_TEXTURE_2D,v->textures[i]);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
            glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
        }
        return handle;
    }
}
void cratelog_turntable_geometry(void *handle,double x,double y,double w,double h,int visible){
    CratelogTurntableView *v=(__bridge CratelogTurntableView *)handle;NSView *parent=v.superview;
    NSRect rect=NSMakeRect(x,parent.isFlipped?y:parent.bounds.size.height-y-h,MAX(1,w),MAX(1,h));
    if(!NSEqualRects(v.frame,rect)){[v setFrame:rect];[v.openGLContext update];}
    v.hidden=!visible;
}
void cratelog_turntable_texture(void *handle,int slot,int w,int h,const void *pixels){
    if(slot<0||slot>4||w<1||h<1)return;
    CratelogTurntableView *v=(__bridge CratelogTurntableView *)handle;[v.openGLContext makeCurrentContext];
    glBindTexture(GL_TEXTURE_2D,v->textures[slot]);glPixelStorei(GL_UNPACK_ALIGNMENT,1);
    glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,pixels);
}
// Rasterize only changed HUD content. CoreText supplies Unicode font fallback.
int cratelog_turntable_hud(void *handle,int slot,int w,int h,const void *pixels,const char *json){
    @autoreleasepool {
        if(w<1||h<1)return 0;
        size_t count=(size_t)w*h,bytes=count*4;
        unsigned char *buffer=calloc(1,bytes);if(!buffer)return 0;
        CGColorSpaceRef space=CGColorSpaceCreateDeviceRGB();
        CGContextRef ctx=CGBitmapContextCreate(buffer,w,h,8,w*4,space,kCGImageAlphaPremultipliedLast|kCGBitmapByteOrder32Big);
        if(!ctx){CGColorSpaceRelease(space);free(buffer);return 0;}
        CGDataProviderRef provider=CGDataProviderCreateWithData(NULL,pixels,bytes,NULL);
        CGImageRef image=CGImageCreate(w,h,8,32,w*4,space,kCGImageAlphaLast|kCGBitmapByteOrder32Big,provider,NULL,false,kCGRenderingIntentDefault);
        if(!image){CGDataProviderRelease(provider);CGContextRelease(ctx);CGColorSpaceRelease(space);free(buffer);return 0;}
        CGContextDrawImage(ctx,CGRectMake(0,0,w,h),image);
        NSData *data=[NSData dataWithBytes:json length:strlen(json)];
        NSArray *texts=[NSJSONSerialization JSONObjectWithData:data options:0 error:NULL];
        NSFont *font=[NSFont systemFontOfSize:22.];
        CTFontRef ctfont=CTFontCreateWithName((__bridge CFStringRef)font.fontName,22.,NULL);
        NSFont *bold=[NSFont boldSystemFontOfSize:22.];
        CTFontRef boldfont=CTFontCreateWithName((__bridge CFStringRef)bold.fontName,22.,NULL);
        NSFont *light=[NSFont systemFontOfSize:22. weight:NSFontWeightLight];
        CTFontRef lightfont=CTFontCreateWithName((__bridge CFStringRef)light.fontName,22.,NULL);
        for(NSArray *entry in texts){
            if(entry.count<4)continue;
            CTFontRef chosen=entry.count>4?([entry[4] boolValue]?boldfont:lightfont):ctfont;
            NSString *hex=entry[3];unsigned rgb=0xffffff;
            if(hex.length==7){NSScanner *scanner=[NSScanner scannerWithString:[hex substringFromIndex:1]];[scanner scanHexInt:&rgb];}
            CGFloat components[]={((rgb>>16)&255)/255.,((rgb>>8)&255)/255.,(rgb&255)/255.,1.};
            CGColorRef color=CGColorCreate(space,components);
            NSDictionary *attributes=@{(__bridge NSString *)kCTFontAttributeName:(__bridge id)chosen,(__bridge NSString *)kCTForegroundColorAttributeName:(__bridge id)color};
            NSAttributedString *string=[[NSAttributedString alloc]initWithString:entry[2] attributes:attributes];
            CTLineRef line=CTLineCreateWithAttributedString((__bridge CFAttributedStringRef)string);
            if(entry.count>5){
                NSAttributedString *token=[[NSAttributedString alloc]initWithString:@"…" attributes:attributes];
                CTLineRef ellipsis=CTLineCreateWithAttributedString((__bridge CFAttributedStringRef)token);
                CTLineRef fitted=CTLineCreateTruncatedLine(line,[entry[5] doubleValue]*2.,kCTLineTruncationEnd,ellipsis);
                if(fitted){CFRelease(line);line=fitted;}CFRelease(ellipsis);
            }
            CGFloat ascent=0,descent=0;CTLineGetTypographicBounds(line,&ascent,&descent,NULL);
            CGContextSetTextMatrix(ctx,CGAffineTransformIdentity);
            CGContextSetTextPosition(ctx,[entry[0] doubleValue]*2.,h-[entry[1] doubleValue]*2.-(ascent-descent)/2.);
            CTLineDraw(line,ctx);CFRelease(line);CGColorRelease(color);
        }
        // The overlay shader expects straight-alpha RGBA, not premultiplied RGB.
        for(size_t i=0;i<count;i++){
            unsigned char *p=buffer+i*4;unsigned a=p[3];
            if(a)for(int c=0;c<3;c++)p[c]=(unsigned char)MIN(255,(p[c]*255u+a/2)/a);
        }
        if(slot!=2){
            for(int row=0;row<h/2;row++)for(int x=0;x<w*4;x++){
                size_t a=(size_t)row*w*4+x,b=(size_t)(h-1-row)*w*4+x;
                unsigned char value=buffer[a];buffer[a]=buffer[b];buffer[b]=value;
            }
        }
        cratelog_turntable_texture(handle,slot,w,h,buffer);
        CFRelease(boldfont);CFRelease(lightfont);
        CFRelease(ctfont);CGImageRelease(image);CGDataProviderRelease(provider);CGContextRelease(ctx);CGColorSpaceRelease(space);free(buffer);return 1;
    }
}
const char *cratelog_turntable_error(void *handle){
    return ((__bridge CratelogTurntableView *)handle)->lastError;
}
static BOOL checkGL(CratelogTurntableView *v,const char *stage){
    GLenum error=glGetError();
    if(error==GL_NO_ERROR)return YES;
    snprintf(v->lastError,sizeof(v->lastError),"%s: OpenGL 0x%04x; renderer=%s; version=%s",stage,error,glGetString(GL_RENDERER),glGetString(GL_VERSION));
    return NO;
}
int cratelog_turntable_render(void *handle,const char *json,int w,int h){
    @autoreleasepool {
        CratelogTurntableView *v=(__bridge CratelogTurntableView *)handle;
        if(v.hidden||v.window.miniaturized||!v.window.visible)return 0;
        NSData *data=[NSData dataWithBytes:json length:strlen(json)];
        NSDictionary *values=[NSJSONSerialization JSONObjectWithData:data options:0 error:NULL];
        if(![values isKindOfClass:NSDictionary.class]){snprintf(v->lastError,sizeof(v->lastError),"Invalid uniform JSON");return -1;}
        [v.openGLContext makeCurrentContext];
        if(!checkGL(v,"context/texture upload"))return -1;
        glBindVertexArray(v->vao);glDisable(GL_BLEND);
        glBindFramebuffer(GL_FRAMEBUFFER,v->fbo);
        if(v->renderWidth!=w||v->renderHeight!=h){
            glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,v->colorTexture);
            glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
            glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAX_LEVEL,0);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
            glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,v->colorTexture,0);
            GLenum status=glCheckFramebufferStatus(GL_FRAMEBUFFER);
            if(status!=GL_FRAMEBUFFER_COMPLETE){snprintf(v->lastError,sizeof(v->lastError),"Scene framebuffer incomplete: 0x%04x (%dx%d)",status,w,h);return -1;}
            v->renderWidth=w;v->renderHeight=h;
        }
        glViewport(0,0,w,h);glUseProgram(v->sceneProgram);
        glUniform2f(glGetUniformLocation(v->sceneProgram,"resolution"),w,h);
        for(NSString *key in values){
            GLint location=glGetUniformLocation(v->sceneProgram,key.UTF8String);id value=values[key];
            if([value isKindOfClass:NSArray.class]){
                NSArray *a=value;GLfloat f[4]={0};for(NSUInteger i=0;i<MIN(4,a.count);i++)f[i]=[a[i] floatValue];
                if(a.count==2)glUniform2fv(location,1,f);else if(a.count==3)glUniform3fv(location,1,f);else if(a.count==4)glUniform4fv(location,1,f);
            }else glUniform1f(location,[value floatValue]);
        }
        for(int i=0;i<2;i++){glActiveTexture(GL_TEXTURE0+i);glBindTexture(GL_TEXTURE_2D,v->textures[i]);}
        glUniform1i(glGetUniformLocation(v->sceneProgram,"cover"),0);glUniform1i(glGetUniformLocation(v->sceneProgram,"panel"),1);
        if(!checkGL(v,"scene uniforms and textures"))return -1;
        glActiveTexture(GL_TEXTURE3);glBindTexture(GL_TEXTURE_2D,v->textures[3]);
        glUniform1i(glGetUniformLocation(v->sceneProgram,"pending_cover"),3);
        glActiveTexture(GL_TEXTURE4);glBindTexture(GL_TEXTURE_2D,v->textures[4]);
        glUniform1i(glGetUniformLocation(v->sceneProgram,"pending_spine"),4);
        glDrawArrays(GL_TRIANGLES,0,6);
        if(!checkGL(v,"scene draw"))return -1;
        NSRect backing=[v convertRectToBacking:v.bounds];int width=MAX(1,(int)backing.size.width),height=MAX(1,(int)backing.size.height);
        // Validate the source and Cocoa destination independently. A valid FBO
        // alone does not imply that the context has a window drawable.
        if(v.openGLContext.view!=v){[v.openGLContext setView:v];[v.openGLContext update];}
        glBindFramebuffer(GL_READ_FRAMEBUFFER,v->fbo);glReadBuffer(GL_COLOR_ATTACHMENT0);
        GLenum sourceStatus=glCheckFramebufferStatus(GL_READ_FRAMEBUFFER);
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER,0);glDrawBuffer(GL_BACK);
        GLenum destinationStatus=glCheckFramebufferStatus(GL_DRAW_FRAMEBUFFER);
        if(destinationStatus!=GL_FRAMEBUFFER_COMPLETE){
            // Window mapping / Retina changes can invalidate the drawable.
            [v.openGLContext setView:v];[v.openGLContext update];[v.openGLContext makeCurrentContext];
            glBindFramebuffer(GL_DRAW_FRAMEBUFFER,0);glDrawBuffer(GL_BACK);
            destinationStatus=glCheckFramebufferStatus(GL_DRAW_FRAMEBUFFER);
        }
        if(sourceStatus!=GL_FRAMEBUFFER_COMPLETE||destinationStatus!=GL_FRAMEBUFFER_COMPLETE){
            snprintf(v->lastError,sizeof(v->lastError),"Presentation framebuffer incomplete: source=0x%04x destination=0x%04x; backing=%dx%d; attached=%d",sourceStatus,destinationStatus,width,height,v.openGLContext.view==v);return -1;
        }
        glBindFramebuffer(GL_READ_FRAMEBUFFER,v->fbo);
        glBlitFramebuffer(0,0,w,h,0,0,width,height,GL_COLOR_BUFFER_BIT,GL_LINEAR);
        if(!checkGL(v,"GPU framebuffer resolve"))return -1;
        glBindFramebuffer(GL_FRAMEBUFFER,0);glViewport(0,0,width,height);glUseProgram(v->overlayProgram);
        glActiveTexture(GL_TEXTURE2);glBindTexture(GL_TEXTURE_2D,v->textures[2]);glUniform1i(glGetUniformLocation(v->overlayProgram,"hud"),2);
        glUniform2f(glGetUniformLocation(v->overlayProgram,"resolution"),width,height);
        glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glDrawArrays(GL_TRIANGLES,0,6);glDisable(GL_BLEND);
        if(!checkGL(v,"HUD draw"))return -1;
        [v.openGLContext flushBuffer];return checkGL(v,"buffer presentation")?1:-1;
    }
}
