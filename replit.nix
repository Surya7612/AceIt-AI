{pkgs}: {
  deps = [
    pkgs.redis
    pkgs.tesseract
    pkgs.postgresql
    pkgs.openssl
  ];
}
