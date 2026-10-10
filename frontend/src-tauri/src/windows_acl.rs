//! Owner-only credential ACLs without PowerShell or domain account lookup.

use std::ffi::c_void;
use std::io;
use std::os::windows::ffi::OsStrExt;
use std::path::Path;
use std::ptr;

#[link(name = "advapi32")]
extern "system" {
    fn OpenProcessToken(process: *mut c_void, access: u32, token: *mut *mut c_void) -> i32;
    fn GetTokenInformation(
        token: *mut c_void,
        class: u32,
        buffer: *mut c_void,
        size: u32,
        needed: *mut u32,
    ) -> i32;
    fn ConvertSidToStringSidW(sid: *mut c_void, text: *mut *mut u16) -> i32;
    fn ConvertStringSecurityDescriptorToSecurityDescriptorW(
        text: *const u16,
        revision: u32,
        descriptor: *mut *mut c_void,
        size: *mut u32,
    ) -> i32;
    fn GetSecurityDescriptorOwner(
        descriptor: *mut c_void,
        owner: *mut *mut c_void,
        defaulted: *mut i32,
    ) -> i32;
    fn GetSecurityDescriptorDacl(
        descriptor: *mut c_void,
        present: *mut i32,
        dacl: *mut *mut c_void,
        defaulted: *mut i32,
    ) -> i32;
    fn SetNamedSecurityInfoW(
        path: *mut u16,
        object_type: u32,
        information: u32,
        owner: *mut c_void,
        group: *mut c_void,
        dacl: *mut c_void,
        sacl: *mut c_void,
    ) -> u32;
}

#[link(name = "kernel32")]
extern "system" {
    fn GetCurrentProcess() -> *mut c_void;
    fn CloseHandle(handle: *mut c_void) -> i32;
    fn LocalFree(memory: *mut c_void) -> *mut c_void;
}

struct Handle(*mut c_void);
impl Drop for Handle {
    fn drop(&mut self) {
        unsafe {
            CloseHandle(self.0);
        }
    }
}

struct LocalMemory(*mut c_void);
impl Drop for LocalMemory {
    fn drop(&mut self) {
        unsafe {
            LocalFree(self.0);
        }
    }
}

fn current_user_sid() -> io::Result<String> {
    unsafe {
        let mut token = ptr::null_mut();
        if OpenProcessToken(GetCurrentProcess(), 0x0008, &mut token) == 0 {
            return Err(io::Error::last_os_error());
        }
        let token = Handle(token);
        let mut size = 0;
        GetTokenInformation(token.0, 1, ptr::null_mut(), 0, &mut size);
        if size == 0 {
            return Err(io::Error::last_os_error());
        }
        // TOKEN_USER contains a pointer; usize storage preserves its alignment.
        let mut buffer = vec![0usize; (size as usize).div_ceil(std::mem::size_of::<usize>())];
        if GetTokenInformation(token.0, 1, buffer.as_mut_ptr().cast(), size, &mut size) == 0 {
            return Err(io::Error::last_os_error());
        }
        let sid = *(buffer.as_ptr() as *const *mut c_void);
        let mut text = ptr::null_mut();
        if ConvertSidToStringSidW(sid, &mut text) == 0 {
            return Err(io::Error::last_os_error());
        }
        let _text = LocalMemory(text.cast());
        let mut length = 0;
        while *text.add(length) != 0 {
            length += 1;
        }
        Ok(String::from_utf16_lossy(std::slice::from_raw_parts(
            text, length,
        )))
    }
}

pub(crate) fn restrict_to_owner(path: &Path) -> io::Result<()> {
    let sid = current_user_sid()?;
    let inheritance = if path.is_dir() { "OICI" } else { "" };
    let sddl: Vec<u16> = format!("O:{sid}D:P(A;{inheritance};FA;;;{sid})")
        .encode_utf16()
        .chain(Some(0))
        .collect();
    let mut path: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
    unsafe {
        let mut descriptor = ptr::null_mut();
        if ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl.as_ptr(),
            1,
            &mut descriptor,
            ptr::null_mut(),
        ) == 0
        {
            return Err(io::Error::last_os_error());
        }
        let descriptor = LocalMemory(descriptor);
        // Owner + protected DACL, with no inherited or unrelated allow ACEs.
        let mut owner = ptr::null_mut();
        let mut defaulted = 0;
        if GetSecurityDescriptorOwner(descriptor.0, &mut owner, &mut defaulted) == 0 {
            return Err(io::Error::last_os_error());
        }
        let mut dacl = ptr::null_mut();
        let mut present = 0;
        if GetSecurityDescriptorDacl(descriptor.0, &mut present, &mut dacl, &mut defaulted) == 0 {
            return Err(io::Error::last_os_error());
        }
        if owner.is_null() || present == 0 || dacl.is_null() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Missing private credential DACL",
            ));
        }
        // Preserve directory inheritance propagation for existing children.
        let status = SetNamedSecurityInfoW(
            path.as_mut_ptr(),
            1,
            0x80000005,
            owner,
            ptr::null_mut(),
            dacl,
            ptr::null_mut(),
        );
        if status != 0 {
            return Err(io::Error::from_raw_os_error(status as i32));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[link(name = "advapi32")]
    extern "system" {
        fn GetFileSecurityW(
            path: *const u16,
            information: u32,
            descriptor: *mut c_void,
            size: u32,
            needed: *mut u32,
        ) -> i32;
        fn ConvertSecurityDescriptorToStringSecurityDescriptorW(
            descriptor: *mut c_void,
            revision: u32,
            information: u32,
            text: *mut *mut u16,
            size: *mut u32,
        ) -> i32;
    }

    fn read_sddl(path: &Path) -> String {
        let path: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
        unsafe {
            let mut size = 0;
            GetFileSecurityW(path.as_ptr(), 5, ptr::null_mut(), 0, &mut size);
            let mut buffer = vec![0usize; (size as usize).div_ceil(std::mem::size_of::<usize>())];
            assert_ne!(
                GetFileSecurityW(
                    path.as_ptr(),
                    5,
                    buffer.as_mut_ptr().cast(),
                    size,
                    &mut size
                ),
                0
            );
            let mut text = ptr::null_mut();
            assert_ne!(
                ConvertSecurityDescriptorToStringSecurityDescriptorW(
                    buffer.as_mut_ptr().cast(),
                    1,
                    5,
                    &mut text,
                    ptr::null_mut()
                ),
                0
            );
            let _text = LocalMemory(text.cast());
            let mut length = 0;
            while *text.add(length) != 0 {
                length += 1;
            }
            String::from_utf16_lossy(std::slice::from_raw_parts(text, length))
        }
    }

    #[test]
    fn secures_open_file_and_directory_without_domain_lookup() {
        let root = std::env::temp_dir().join(format!("lambchat-native-acl-{}", std::process::id()));
        std::fs::create_dir_all(&root).unwrap();
        let file = root.join("quote'; $(command).tmp");
        let handle = std::fs::File::create(&file).unwrap();
        restrict_to_owner(&file).unwrap();
        let sid = current_user_sid().unwrap();
        assert_eq!(
            read_sddl(&file).replace("D:PAI", "D:P"),
            format!("O:{sid}D:P(A;;FA;;;{sid})")
        );
        drop(handle);
        let existing = root.join("existing");
        std::fs::write(&existing, b"synthetic").unwrap();
        restrict_to_owner(&root).unwrap();
        assert_eq!(
            read_sddl(&root).replace("D:PAI", "D:P"),
            format!("O:{sid}D:P(A;OICI;FA;;;{sid})")
        );
        assert_eq!(read_sddl(&existing).matches("(A;").count(), 1);
        assert!(read_sddl(&existing).contains(&format!(";FA;;;{sid})")));
        assert!(restrict_to_owner(&root.join("missing")).is_err());
        std::fs::remove_dir_all(root).unwrap();
    }
}
