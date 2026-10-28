// App-local pinch/precise-scroll events for the Tk image viewer. Main thread only.
#import <Cocoa/Cocoa.h>
#include <math.h>
#ifndef CRATELOG_GESTURE_HASH
#define CRATELOG_GESTURE_HASH "untracked"
#endif
const char *cratelog_gesture_hash(void) { return CRATELOG_GESTURE_HASH; }
typedef struct { double kind, a, b, x, y; } PictureEvent;
@interface CratelogGestures : NSObject {
@public
    PictureEvent events[256];
    unsigned head, tail;
}
@property(strong) id monitor;
@property(weak) NSView *view;
@property NSRect region;
@end
@implementation CratelogGestures
@end
void *cratelog_gestures_create(void *parent) {
    NSView *view=(__bridge NSView *)parent;
    if (!view || !view.window) return NULL;
    CratelogGestures *state=[CratelogGestures new];state.view=view;
    __weak CratelogGestures *weak=state;
    state.monitor=[NSEvent addLocalMonitorForEventsMatchingMask:(NSEventMaskMagnify|NSEventMaskScrollWheel) handler:^NSEvent *(NSEvent *event) {
        CratelogGestures *s=weak;NSView *v=s.view;
        if (!s || !v || event.window!=v.window || !v.window.visible) return event;
        NSPoint p=[v convertPoint:event.locationInWindow fromView:nil];
        double y=v.isFlipped ? p.y-NSMinY(v.bounds) : NSMaxY(v.bounds)-p.y;
        NSPoint top=NSMakePoint(p.x-NSMinX(v.bounds),y);
        if (!NSPointInRect(top,s.region)) return event;
        PictureEvent e={0};e.x=top.x-s.region.origin.x;e.y=top.y-s.region.origin.y;
        if (event.type==NSEventTypeMagnify) {
            e.kind=1;e.a=1.0+event.magnification;
            if (!isfinite(e.a) || e.a<=0) return nil;
        } else if (event.hasPreciseScrollingDeltas) {
            e.kind=2;e.a=event.scrollingDeltaX;e.b=event.scrollingDeltaY;
        } else return event; // Physical mouse wheel stays with Tk.
        unsigned next=(s->tail+1)%256;
        if (next==s->head) s->head=(s->head+1)%256;
        s->events[s->tail]=e;s->tail=next;
        return nil;
    }];
    if (!state.monitor) return NULL;
    return (__bridge_retained void *)state;
}
void cratelog_gestures_region(void *handle,double x,double y,double w,double h) {
    CratelogGestures *s=(__bridge CratelogGestures *)handle;s.region=NSMakeRect(x,y,w,h);
}
int cratelog_gestures_pop(void *handle,double *out) {
    CratelogGestures *s=(__bridge CratelogGestures *)handle;
    if (s->head==s->tail) return 0;
    PictureEvent e=s->events[s->head];s->head=(s->head+1)%256;
    out[0]=e.kind;out[1]=e.a;out[2]=e.b;out[3]=e.x;out[4]=e.y;return 1;
}
void cratelog_gestures_destroy(void *handle) {
    if (!handle) return;
    CratelogGestures *s=(__bridge_transfer CratelogGestures *)handle;
    [NSEvent removeMonitor:s.monitor];s.monitor=nil;
}
