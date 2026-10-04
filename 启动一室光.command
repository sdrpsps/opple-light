#!/bin/zsh
cd -- "$(dirname -- "$0")" || exit 1
python3 start-macos.py --no-build
if [ $? -ne 0 ]; then
  print "启动未完成。请确认 Docker 引擎已运行；首次部署请运行 python3 start-macos.py 构建镜像。"
  read -r "?按回车关闭窗口。"
  exit 1
fi
print "\n网页登录口令："
docker compose -f compose.macos-relay.yaml exec -T light cat /data/access-token
open http://localhost:8080
print "\n服务已在后台运行，可以关闭此窗口。"
