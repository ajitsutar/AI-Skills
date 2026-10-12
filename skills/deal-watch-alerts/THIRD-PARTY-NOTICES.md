# Third-party notices

The skill's code and documentation use the bundled [MIT license](LICENSE).
No external package implementation, browser executable, merchant content or
notification service is bundled in this folder. The attribution review is
described in [Provenance](PROVENANCE.md).

## Runtime dependencies

| Component | Use | Terms and canonical source |
| --- | --- | --- |
| Python standard library | JSON memory, canonical keys, file locks and command-line helper | Installed separately with Python; [Python license](https://docs.python.org/3/license.html) |
| PyYAML, optional | Reading YAML watch configuration through `yaml.safe_load`; unnecessary for JSON configuration | Installed separately; [canonical repository](https://github.com/yaml/pyyaml), [MIT license](https://github.com/yaml/pyyaml/blob/main/LICENSE) |

The helper imports PyYAML when YAML configuration is requested. It does not copy
or redistribute that package. If a future distribution bundles dependencies,
retain their license and copyright notices, including any additional components
that distribution includes.

## Services and content

Retailers, marketplaces, deal forums, browser tools and notification providers
retain their own access terms and content rights. Their names in examples do not
imply affiliation or a license to reproduce their content. The skill's MIT license
does not grant access to accounts, permission to send notifications, or rights to
redistribute third-party listings, images or text.
