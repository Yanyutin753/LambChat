//! Minimal typed UserNotifications selectors for weak framework loading.
//! Signatures follow objc2-user-notifications 0.3.2 generated bindings (MIT).
//! That crate autolinks the framework strongly, which would break macOS 10.13.
#![allow(non_snake_case)] // Preserve the audited Objective-C selector names.
use block2::DynBlock;
use objc2::{
    extern_class, extern_conformance, extern_methods, extern_protocol,
    rc::Retained,
    runtime::{Bool, ProtocolObject},
};
use objc2_foundation::{NSDictionary, NSError, NSObject, NSObjectProtocol, NSString, NSUInteger};

pub type UNAuthorizationOptions = NSUInteger;
pub type UNNotificationPresentationOptions = NSUInteger;
pub const UN_AUTHORIZATION_ALERT: UNAuthorizationOptions = 4;

extern_class!(
    #[unsafe(super(NSObject))]
    pub struct UNUserNotificationCenter;
);
extern_class!(
    #[unsafe(super(NSObject))]
    pub struct UNNotification;
);
extern_class!(
    #[unsafe(super(NSObject))]
    pub struct UNNotificationRequest;
);
extern_class!(
    #[unsafe(super(NSObject))]
    pub struct UNNotificationContent;
);
extern_class!(
    #[unsafe(super(UNNotificationContent, NSObject))]
    pub struct UNMutableNotificationContent;
);
extern_class!(
    #[unsafe(super(NSObject))]
    pub struct UNNotificationResponse;
);
extern_class!(
    #[unsafe(super(NSObject))]
    pub struct UNNotificationTrigger;
);

extern_conformance!(
    unsafe impl NSObjectProtocol for UNUserNotificationCenter {}
);
extern_conformance!(
    unsafe impl NSObjectProtocol for UNNotification {}
);
extern_conformance!(
    unsafe impl NSObjectProtocol for UNNotificationRequest {}
);
extern_conformance!(
    unsafe impl NSObjectProtocol for UNNotificationContent {}
);
extern_conformance!(
    unsafe impl NSObjectProtocol for UNMutableNotificationContent {}
);
extern_conformance!(
    unsafe impl NSObjectProtocol for UNNotificationResponse {}
);
extern_conformance!(
    unsafe impl NSObjectProtocol for UNNotificationTrigger {}
);

impl UNUserNotificationCenter {
    extern_methods!(
        #[unsafe(method(currentNotificationCenter))]
        #[unsafe(method_family = none)]
        pub fn currentNotificationCenter() -> Retained<Self>;
        #[unsafe(method(setDelegate:))]
        #[unsafe(method_family = none)]
        pub fn setDelegate(
            &self,
            delegate: Option<&ProtocolObject<dyn UNUserNotificationCenterDelegate>>,
        );
        #[unsafe(method(requestAuthorizationWithOptions:completionHandler:))]
        #[unsafe(method_family = none)]
        pub fn requestAuthorizationWithOptions_completionHandler(
            &self,
            options: UNAuthorizationOptions,
            completion: &DynBlock<dyn Fn(Bool, *mut NSError)>,
        );
        #[unsafe(method(addNotificationRequest:withCompletionHandler:))]
        #[unsafe(method_family = none)]
        pub fn addNotificationRequest_withCompletionHandler(
            &self,
            request: &UNNotificationRequest,
            completion: Option<&DynBlock<dyn Fn(*mut NSError)>>,
        );
    );
}
impl UNMutableNotificationContent {
    extern_methods!(
        #[unsafe(method(new))]
        #[unsafe(method_family = new)]
        pub fn new() -> Retained<Self>;
        #[unsafe(method(setTitle:))]
        #[unsafe(method_family = none)]
        pub fn setTitle(&self, title: &NSString);
        #[unsafe(method(setBody:))]
        #[unsafe(method_family = none)]
        pub fn setBody(&self, body: &NSString);
        #[unsafe(method(setUserInfo:))]
        #[unsafe(method_family = none)]
        pub unsafe fn setUserInfo(&self, info: &NSDictionary);
    );
}
impl UNNotificationContent {
    extern_methods!(
        #[unsafe(method(userInfo))]
        #[unsafe(method_family = none)]
        pub fn userInfo(&self) -> Retained<NSDictionary>;
    );
}
impl UNNotificationRequest {
    extern_methods!(
        #[unsafe(method(requestWithIdentifier:content:trigger:))]
        #[unsafe(method_family = none)]
        pub fn requestWithIdentifier_content_trigger(
            identifier: &NSString,
            content: &UNNotificationContent,
            trigger: Option<&UNNotificationTrigger>,
        ) -> Retained<Self>;
        #[unsafe(method(content))]
        #[unsafe(method_family = none)]
        pub fn content(&self) -> Retained<UNNotificationContent>;
    );
}
impl UNNotification {
    extern_methods!(
        #[unsafe(method(request))]
        #[unsafe(method_family = none)]
        pub fn request(&self) -> Retained<UNNotificationRequest>;
    );
}
impl UNNotificationResponse {
    extern_methods!(
        #[unsafe(method(notification))]
        #[unsafe(method_family = none)]
        pub fn notification(&self) -> Retained<UNNotification>;
        #[unsafe(method(actionIdentifier))]
        #[unsafe(method_family = none)]
        pub fn actionIdentifier(&self) -> Retained<NSString>;
    );
}
extern_protocol!(
    pub unsafe trait UNUserNotificationCenterDelegate: NSObjectProtocol {
        #[optional]
        #[unsafe(method(userNotificationCenter:willPresentNotification:withCompletionHandler:))]
        #[unsafe(method_family = none)]
        fn userNotificationCenter_willPresentNotification_withCompletionHandler(
            &self,
            center: &UNUserNotificationCenter,
            notification: &UNNotification,
            completion: &DynBlock<dyn Fn(UNNotificationPresentationOptions)>,
        );
        #[optional]
        #[unsafe(method(userNotificationCenter:didReceiveNotificationResponse:withCompletionHandler:))]
        #[unsafe(method_family = none)]
        fn userNotificationCenter_didReceiveNotificationResponse_withCompletionHandler(
            &self,
            center: &UNUserNotificationCenter,
            response: &UNNotificationResponse,
            completion: &DynBlock<dyn Fn()>,
        );
    }
);

pub fn default_action_identifier() -> Option<&'static NSString> {
    // Do not statically reference a framework symbol absent on macOS 10.13.
    // This immutable NSString constant is Apple-owned after the weak framework loads.
    unsafe {
        let symbol = libc::dlsym(
            libc::RTLD_DEFAULT,
            c"UNNotificationDefaultActionIdentifier".as_ptr(),
        );
        if symbol.is_null() {
            return None;
        }
        (*symbol.cast::<*const NSString>()).as_ref()
    }
}
