<?php

declare(strict_types=1);

$i = 1;
$cfg['Servers'][$i]['auth_type'] = 'config';
$cfg['Servers'][$i]['host'] = getenv('PMA_HOST') ?: 'mariadb';
$cfg['Servers'][$i]['port'] = (int) (getenv('PMA_PORT') ?: 3306);
$cfg['Servers'][$i]['AllowNoPassword'] = false;
$cfg['Servers'][$i]['user'] = getenv('PHPMYADMIN_AUTOLOGIN_USER') ?: '';
$cfg['Servers'][$i]['password'] = getenv('PHPMYADMIN_AUTOLOGIN_PASSWORD') ?: '';
$cfg['Servers'][$i]['only_db'] = [getenv('MARIADB_DATABASE') ?: 'appdb'];
