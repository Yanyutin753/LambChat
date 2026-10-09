//! Independently signed release metadata; the server cannot authorize an update.
use ring::signature::{UnparsedPublicKey, ED25519};
use serde::de::{MapAccess, Visitor};
use serde::{Deserialize, Deserializer};
use std::collections::BTreeMap;

pub const MAX_MANIFEST_BYTES: usize = 2 * 1024 * 1024;
const MAX_ASSET_BYTES: u64 = 1024 * 1024 * 1024;
const RELEASE_PUBLIC_KEY: [u8; 32] = [
    0x89, 0x59, 0x61, 0x86, 0xed, 0xa3, 0x63, 0x9e, 0xcb, 0x3a, 0xa0, 0xe3, 0xe8, 0x7c, 0x31, 0x31,
    0x68, 0xad, 0xd1, 0xfc, 0x4a, 0xc0, 0xb2, 0xc2, 0xe9, 0x84, 0xe2, 0xc3, 0x34, 0xfc, 0x53, 0x62,
];

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SignedAsset {
    pub size: u64,
    pub sha256: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    schema: u8,
    version: String,
    commit: String,
    #[serde(deserialize_with = "unique_assets")]
    assets: BTreeMap<String, SignedAsset>,
}

fn unique_assets<'de, D: Deserializer<'de>>(
    deserializer: D,
) -> Result<BTreeMap<String, SignedAsset>, D::Error> {
    struct Assets;
    impl<'de> Visitor<'de> for Assets {
        type Value = BTreeMap<String, SignedAsset>;
        fn expecting(&self, formatter: &mut std::fmt::Formatter) -> std::fmt::Result {
            formatter.write_str("unique signed assets")
        }
        fn visit_map<M: MapAccess<'de>>(self, mut map: M) -> Result<Self::Value, M::Error> {
            let mut assets = BTreeMap::new();
            while let Some((name, asset)) = map.next_entry::<String, SignedAsset>()? {
                if assets.insert(name, asset).is_some() || assets.len() > 128 {
                    return Err(serde::de::Error::custom("invalid signed assets"));
                }
            }
            Ok(assets)
        }
    }
    deserializer.deserialize_map(Assets)
}

pub fn version_parts(version: &str) -> Result<[u64; 3], String> {
    if version.len() > 32 {
        return Err("Invalid release version".into());
    }
    let mut parts = version.split('.');
    let mut value = [0; 3];
    for item in &mut value {
        let part = parts.next().ok_or("Invalid release version")?;
        if part.is_empty() || !part.bytes().all(|b| b.is_ascii_digit()) {
            return Err("Invalid release version".into());
        }
        *item = part.parse().map_err(|_| "Invalid release version")?;
    }
    if parts.next().is_some() {
        return Err("Invalid release version".into());
    }
    Ok(value)
}

fn lower_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

pub fn verify_release(
    payload: &[u8],
    signature: &[u8],
    version: &str,
    name: &str,
    current: &str,
) -> Result<SignedAsset, String> {
    verify_with_key(
        payload,
        signature,
        version,
        name,
        current,
        &RELEASE_PUBLIC_KEY,
    )
}

fn verify_with_key(
    payload: &[u8],
    signature: &[u8],
    version: &str,
    name: &str,
    current: &str,
    key: &[u8],
) -> Result<SignedAsset, String> {
    let error = "Release signature verification failed";
    if payload.len() > MAX_MANIFEST_BYTES || signature.len() != 64 {
        return Err(error.into());
    }
    UnparsedPublicKey::new(&ED25519, key)
        .verify(payload, signature)
        .map_err(|_| error)?;
    let manifest: Manifest = serde_json::from_slice(payload).map_err(|_| error)?;
    if manifest.schema != 1
        || manifest.version != version
        || version_parts(version)? <= version_parts(current)?
        || !lower_hex(&manifest.commit, 40)
        || manifest.assets.is_empty()
    {
        return Err(error.into());
    }
    for (name, asset) in &manifest.assets {
        if name.is_empty()
            || name.len() > 256
            || !name.as_bytes()[0].is_ascii_alphanumeric()
            || !name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"._+-".contains(&b))
            || asset.size == 0
            || asset.size > MAX_ASSET_BYTES
            || !lower_hex(&asset.sha256, 64)
        {
            return Err(error.into());
        }
    }
    manifest
        .assets
        .get(name)
        .cloned()
        .ok_or_else(|| error.into())
}

pub fn verify_package(path: &std::path::Path, asset: &SignedAsset) -> Result<(), String> {
    use std::io::Read;
    let error = "Update package does not match signed release metadata";
    let metadata = std::fs::symlink_metadata(path).map_err(|_| error)?;
    if !metadata.is_file() || metadata.len() != asset.size {
        return Err(error.into());
    }
    let mut file = std::fs::File::open(path).map_err(|_| error)?;
    let mut digest = ring::digest::Context::new(&ring::digest::SHA256);
    let mut buffer = [0; 64 * 1024];
    let mut total = 0u64;
    loop {
        let count = file.read(&mut buffer).map_err(|_| error)?;
        if count == 0 {
            break;
        }
        total += count as u64;
        if total > asset.size {
            return Err(error.into());
        }
        digest.update(&buffer[..count]);
    }
    let hash: String = digest
        .finish()
        .as_ref()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect();
    if total != asset.size || hash != asset.sha256 {
        return Err(error.into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use ring::signature::{Ed25519KeyPair, KeyPair};

    fn envelope(version: &str) -> (Vec<u8>, Ed25519KeyPair) {
        let key = Ed25519KeyPair::from_seed_unchecked(&[7; 32]).unwrap();
        let payload = format!(r#"{{"schema":1,"version":"{version}","commit":"{}","assets":{{"package.deb":{{"size":3,"sha256":"{}"}}}}}}"#, "a".repeat(40), "b".repeat(64)).into_bytes();
        (payload, key)
    }

    #[test]
    fn cached_package_must_match_signed_size_and_digest() {
        let path = std::env::temp_dir().join(format!("signed-package-{}", uuid::Uuid::new_v4()));
        let body = b"package";
        std::fs::write(&path, body).unwrap();
        let asset = SignedAsset {
            size: body.len() as u64,
            sha256: ring::digest::digest(&ring::digest::SHA256, body)
                .as_ref()
                .iter()
                .map(|b| format!("{b:02x}"))
                .collect(),
        };
        assert!(verify_package(&path, &asset).is_ok());
        std::fs::write(&path, b"tampered").unwrap();
        assert!(verify_package(&path, &asset).is_err());
        std::fs::write(&path, b"packagE").unwrap();
        assert!(verify_package(&path, &asset).is_err());
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    fn signed_release_binds_version_asset_size_and_digest() {
        let (payload, key) = envelope("2.15.0");
        let asset = verify_with_key(
            &payload,
            key.sign(&payload).as_ref(),
            "2.15.0",
            "package.deb",
            "2.14.4",
            key.public_key().as_ref(),
        )
        .unwrap();
        assert_eq!(asset.size, 3);
        assert_eq!(asset.sha256, "b".repeat(64));
    }

    #[test]
    fn rejects_forgery_rollback_version_mismatch_and_unsigned_asset() {
        let (payload, key) = envelope("2.15.0");
        for (version, asset, current) in [
            ("2.15.0", "package.deb", "2.15.0"),
            ("2.16.0", "package.deb", "2.14.4"),
            ("2.15.0", "other.deb", "2.14.4"),
        ] {
            assert!(verify_with_key(
                &payload,
                key.sign(&payload).as_ref(),
                version,
                asset,
                current,
                key.public_key().as_ref()
            )
            .is_err());
        }
        assert!(verify_with_key(
            &payload,
            &[0; 64],
            "2.15.0",
            "package.deb",
            "2.14.4",
            key.public_key().as_ref()
        )
        .is_err());
    }

    #[test]
    fn rejects_duplicate_fields_even_with_valid_signature() {
        let (payload, key) = envelope("2.15.0");
        let mut value = String::from_utf8(payload).unwrap();
        value = value.replace("\"size\":3", "\"size\":3,\"size\":4");
        assert!(verify_with_key(
            value.as_bytes(),
            key.sign(value.as_bytes()).as_ref(),
            "2.15.0",
            "package.deb",
            "2.14.4",
            key.public_key().as_ref()
        )
        .is_err());
    }
}
