const releaseAssets = [
  {
    path: "dist/agentcart-shopbridge.zip",
    label: "AgentCart ShopBridge WooCommerce plugin ZIP",
  },
  {
    path: "dist/shopbridge-direct-skill.zip",
    label: "AgentCart ShopBridge direct buyer skill ZIP",
  },
  {
    path: "dist/agentcart-release.json",
    label: "AgentCart release manifest with artifact checksums",
  },
];

module.exports = {
  branches: ["main"],
  tagFormat: "v${version}",
  plugins: [
    "@semantic-release/commit-analyzer",
    "@semantic-release/release-notes-generator",
    [
      "@semantic-release/exec",
      {
        verifyReleaseCmd: "python3 scripts/stamp-release-version.py ${nextRelease.version} --check",
        prepareCmd: "scripts/prepare-semantic-release.sh ${nextRelease.version} ${nextRelease.gitHead}",
      },
    ],
    [
      "@semantic-release/github",
      {
        assets: releaseAssets,
        successComment: false,
        failComment: false,
      },
    ],
  ],
};
