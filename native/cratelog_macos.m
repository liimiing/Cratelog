// Tk-owned Cocoa subview + libmpv Render API. No Python callbacks or pixel copies.
// All exported functions and AppKit operations run on the Tk/main thread.
#import <Cocoa/Cocoa.h>
#import <OpenGL/gl3.h>
#include <mpv/client.h>
#include <mpv/render_gl.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <limits.h>

#ifndef CRATELOG_SOURCE_SHA256
#define CRATELOG_SOURCE_SHA256 "untracked"
#endif
int cratelog_bridge_version(void) { return 2; }
const char *cratelog_source_sha256(void) { return CRATELOG_SOURCE_SHA256; }

@interface CratelogGLView : NSOpenGLView {
@public
    mpv_handle *player;
    mpv_render_context *renderer;
    atomic_bool dirty;
    uint64_t frames;
}
@property(strong) NSTimer *timer;
- (void)shutdown;
@end

static void *resolve_gl(void *ctx, const char *name) {
    return dlsym(RTLD_DEFAULT, name);
}
static void updated(void *ctx) {
    // libmpv's worker must never enter AppKit or call another mpv API.
    CratelogGLView *view = (__bridge CratelogGLView *)ctx;
    atomic_store(&view->dirty, true);
}

@implementation CratelogGLView
- (BOOL)isOpaque { return YES; }
// Tk retains hit testing, focus, drag/seek and keyboard handling.
- (NSView *)hitTest:(NSPoint)point { return nil; }
- (void)drawRect:(NSRect)rect {
    if (!renderer) return;
    [[self openGLContext] makeCurrentContext];
    NSRect pixels = [self convertRectToBacking:self.bounds];
    mpv_opengl_fbo fbo = {0, MAX(1, (int)pixels.size.width), MAX(1, (int)pixels.size.height), 0};
    int flip = 1, block = 0;
    mpv_render_param params[] = {
        {MPV_RENDER_PARAM_OPENGL_FBO, &fbo},
        {MPV_RENDER_PARAM_FLIP_Y, &flip},
        // Waiting for the media clock here would block Tk's entire UI.
        {MPV_RENDER_PARAM_BLOCK_FOR_TARGET_TIME, &block}, {0}
    };
    mpv_render_context_render(renderer, params);
    [[self openGLContext] flushBuffer];
    mpv_render_context_report_swap(renderer);
    frames++;
}
- (void)reshape {
    [super reshape];
    [[self openGLContext] update];
    atomic_store(&dirty, true);
}
- (void)viewDidChangeBackingProperties {
    [super viewDidChangeBackingProperties];
    atomic_store(&dirty, true);
}
- (void)shutdown {
    [self.timer invalidate]; self.timer = nil;
    if (renderer) {
        mpv_render_context_set_update_callback(renderer, NULL, NULL);
        [[self openGLContext] makeCurrentContext];
        mpv_render_context_free(renderer); renderer = NULL;
    }
    if (player) { mpv_terminate_destroy(player); player = NULL; }
    [self removeFromSuperview];
    [self clearGLContext];
}
@end

void *cratelog_create(void *parent, const char *options_json, char *error, size_t capacity) {
    @autoreleasepool {
        if (![NSThread isMainThread] || !parent) {
            snprintf(error, capacity, "Native renderer requires a Tk NSView on the main thread"); return NULL;
        }
        NSOpenGLPixelFormatAttribute attrs[] = {
            NSOpenGLPFAOpenGLProfile, NSOpenGLProfileVersion3_2Core,
            NSOpenGLPFAAccelerated, NSOpenGLPFADoubleBuffer,
            NSOpenGLPFAColorSize, 24, 0
        };
        NSOpenGLPixelFormat *format = [[NSOpenGLPixelFormat alloc] initWithAttributes:attrs];
        CratelogGLView *view = [[CratelogGLView alloc] initWithFrame:NSMakeRect(0,0,32,32) pixelFormat:format];
        if (!format || !view || !view.openGLContext) {
            snprintf(error, capacity, "Cannot create accelerated OpenGL 3.2 context"); return NULL;
        }
        atomic_init(&view->dirty, true);
        // Tk anchors this fixed-height plot to the top. Cocoa uses bottom-origin
        // coordinates, so parent-height changes must move its bottom margin.
        // Fullscreen/titlebar transitions can resize Cocoa before Tk Configure.
        view.autoresizingMask = [(__bridge NSView *)parent isFlipped]
            ? NSViewMaxYMargin : NSViewMinYMargin;
        view.wantsBestResolutionOpenGLSurface = YES;
        view->player = mpv_create();
        int status = view->player ? 0 : MPV_ERROR_NOMEM;
        const char *stage = "mpv_create";
        NSData *data = [NSData dataWithBytes:options_json length:strlen(options_json)];
        NSDictionary *options = [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL];
        if (![options isKindOfClass:NSDictionary.class]) {
            status = MPV_ERROR_INVALID_PARAMETER; stage = "options JSON";
        }
        if (status >= 0) {
            for (NSString *key in options) {
                id value = options[key];
                if ([value isKindOfClass:NSArray.class]) {
                    NSArray *items = value;
                    if (items.count > INT_MAX) status = MPV_ERROR_INVALID_PARAMETER;
                    else {
                        mpv_node *values = calloc(MAX(1, items.count), sizeof(mpv_node));
                        status = values ? 0 : MPV_ERROR_NOMEM;
                        if (values) {
                            for (NSUInteger i = 0; i < items.count; i++) {
                                if (![items[i] isKindOfClass:NSString.class]) {
                                    status = MPV_ERROR_INVALID_PARAMETER; break;
                                }
                                values[i].format = MPV_FORMAT_STRING;
                                values[i].u.string = (char *)[items[i] UTF8String];
                            }
                            mpv_node_list list = {.num=(int)items.count, .values=values};
                            mpv_node node = {.format=MPV_FORMAT_NODE_ARRAY, .u.list=&list};
                            if (status >= 0) status = mpv_set_option(view->player, key.UTF8String, MPV_FORMAT_NODE, &node);
                            free(values);
                        }
                    }
                } else if ([value isKindOfClass:NSString.class]) {
                    status = mpv_set_option_string(view->player, key.UTF8String, [value UTF8String]);
                } else status = MPV_ERROR_INVALID_PARAMETER;
                if (status < 0) {
                    snprintf(error, capacity, "libmpv option '%s': %s (%d)",
                             key.UTF8String, mpv_error_string(status), status);
                    [view shutdown]; return NULL;
                }
            }
        }
        if (status >= 0) { stage = "mpv_initialize"; status = mpv_initialize(view->player); }
        if (status >= 0) {
            [(__bridge NSView *)parent addSubview:view];
            [[view openGLContext] makeCurrentContext];
            // mpv schedules frames; disable blocking swap on Tk's UI thread.
            GLint interval = 0;
            [[view openGLContext] setValues:&interval forParameter:NSOpenGLCPSwapInterval];
            mpv_opengl_init_params gl = {resolve_gl, NULL};
            mpv_render_param params[] = {
                {MPV_RENDER_PARAM_API_TYPE, MPV_RENDER_API_TYPE_OPENGL},
                {MPV_RENDER_PARAM_OPENGL_INIT_PARAMS, &gl}, {0}
            };
            stage = "mpv_render_context_create";
            status = mpv_render_context_create(&view->renderer, view->player, params);
        }
        if (status < 0) {
            snprintf(error, capacity, "libmpv %s: %s (%d)", stage, mpv_error_string(status), status);
            [view shutdown]; return NULL;
        }
        mpv_render_context_set_update_callback(view->renderer, updated, (__bridge void *)view);
        __weak CratelogGLView *weakView = view;
        view.timer = [NSTimer timerWithTimeInterval:1.0/60.0 repeats:YES block:^(NSTimer *timer) {
            CratelogGLView *v = weakView;
            if (!v || !v->renderer) return;
            if (atomic_exchange(&v->dirty, false)) {
                // Continue consuming frames even when minimized so VO cannot stall audio.
                mpv_render_context_update(v->renderer);
                [v drawRect:v.bounds];
            }
        }];
        [[NSRunLoop mainRunLoop] addTimer:view.timer forMode:NSRunLoopCommonModes];
        return (__bridge_retained void *)view;
    }
}

void cratelog_geometry(void *handle, double x, double y, double w, double h, int visible) {
    CratelogGLView *view = (__bridge CratelogGLView *)handle;
    NSView *parent = view.superview;
    double bottom = parent.isFlipped ? y : parent.bounds.size.height-y-h;
    [view setFrame:NSMakeRect(x, bottom, MAX(1,w), MAX(1,h))];
    view.hidden = !visible;
    atomic_store(&view->dirty, true);
}
uint64_t cratelog_frames(void *handle) {
    return ((__bridge CratelogGLView *)handle)->frames;
}
// Diagnostic only: all coordinates are Cocoa points except backing dimensions.
void cratelog_geometry_snapshot(void *handle, double *out) {
    CratelogGLView *view = (__bridge CratelogGLView *)handle;
    NSView *parent = view.superview;
    NSRect frame=view.frame, bounds=parent.bounds;
    NSRect pixels=[view convertRectToBacking:view.bounds];
    double values[]={parent.isFlipped, bounds.origin.x, bounds.origin.y,
        bounds.size.width,bounds.size.height,frame.origin.x,frame.origin.y,
        frame.size.width,frame.size.height,pixels.size.width,pixels.size.height};
    memcpy(out,values,sizeof(values));
}
void cratelog_destroy(void *handle) {
    CratelogGLView *view = (__bridge_transfer CratelogGLView *)handle;
    [view shutdown];
}
