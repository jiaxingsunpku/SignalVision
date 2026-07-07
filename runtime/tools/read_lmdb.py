#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取LMDB数据库文件的工具脚本
用于查看LibSignal生成的训练/测试数据集
"""

import lmdb
import argparse
import os
from pathlib import Path


def read_lmdb(db_path, show_all=False, max_items=10, search_key=None):
    """
    读取LMDB数据库
    
    参数:
        db_path: 数据库路径（包含data.mdb和lock.mdb的目录）
        show_all: 是否显示所有条目
        max_items: 最多显示的条目数（当show_all=False时）
        search_key: 要搜索的特定键
    """
    # 确定数据库路径
    if db_path.endswith('.mdb'):
        db_path = os.path.dirname(db_path)
    
    if not os.path.exists(db_path):
        print(f"错误: 路径不存在: {db_path}")
        return
    
    print("="*60)
    print(f"LMDB 数据库: {db_path}")
    print("="*60)
    
    try:
        # 打开数据库（只读模式）
        env = lmdb.open(db_path, subdir=True, readonly=True, lock=False)
        
        # 获取数据库统计信息
        stat = env.stat()
        info = env.info()
        
        print(f"\n数据库统计信息:")
        print(f"  条目数量: {stat['entries']}")
        print(f"  页面大小: {stat['psize']} bytes")
        print(f"  树深度: {stat['depth']}")
        print(f"  地图大小: {info['map_size'] / (1024*1024):.2f} MB")
        
        # 开始事务读取数据
        with env.begin() as txn:
            cursor = txn.cursor()
            
            # 如果指定了搜索键
            if search_key:
                print(f"\n搜索键: '{search_key}'")
                value = txn.get(search_key.encode())
                if value:
                    decoded_value = value.decode()
                    print(f"值: {decoded_value[:500]}...")  # 限制显示长度
                    try:
                        parsed = eval(decoded_value)
                        print(f"\n解析后的数据类型: {type(parsed)}")
                        if isinstance(parsed, dict):
                            print(f"字典键: {list(parsed.keys())}")
                        elif isinstance(parsed, (list, tuple)):
                            print(f"列表长度: {len(parsed)}")
                    except:
                        pass
                else:
                    print("未找到该键")
                return
            
            # 显示所有或部分条目
            print(f"\n数据条目{'（全部）' if show_all else f'（前{max_items}条）'}:")
            print("-"*60)
            
            count = 0
            for key, value in cursor:
                if not show_all and count >= max_items:
                    remaining = stat['entries'] - count
                    print(f"\n... 还有 {remaining} 条记录未显示 ...")
                    break
                
                key_str = key.decode()
                value_str = value.decode()
                
                # 限制值的显示长度
                if len(value_str) > 200:
                    value_display = value_str[:200] + "..."
                else:
                    value_display = value_str
                
                print(f"\n键: {key_str}")
                print(f"值: {value_display}")
                
                count += 1
            
            if count == 0:
                print("数据库为空")
        
        env.close()
        
    except Exception as e:
        print(f"错误: 无法读取数据库: {e}")
        import traceback
        traceback.print_exc()


def list_keys(db_path, pattern=None):
    """列出所有键"""
    if db_path.endswith('.mdb'):
        db_path = os.path.dirname(db_path)
    
    try:
        env = lmdb.open(db_path, subdir=True, readonly=True, lock=False)
        
        with env.begin() as txn:
            cursor = txn.cursor()
            keys = []
            
            for key, _ in cursor:
                key_str = key.decode()
                if pattern is None or pattern in key_str:
                    keys.append(key_str)
            
            print(f"\n找到 {len(keys)} 个键" + (f"（匹配 '{pattern}'）" if pattern else ""))
            
            # 显示前20个
            for k in keys[:20]:
                print(f"  {k}")
            
            if len(keys) > 20:
                print(f"  ... 还有 {len(keys) - 20} 个键")
        
        env.close()
        
    except Exception as e:
        print(f"错误: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='读取LMDB数据库文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 查看数据库基本信息和前10条记录
  python read_lmdb.py /path/to/dataset
  
  # 查看所有记录
  python read_lmdb.py /path/to/dataset --all
  
  # 搜索特定键
  python read_lmdb.py /path/to/dataset --key "0_1"
  
  # 列出所有键
  python read_lmdb.py /path/to/dataset --list-keys
  
  # 列出匹配模式的键
  python read_lmdb.py /path/to/dataset --list-keys --pattern "0_"
        """
    )
    
    parser.add_argument('--db_path',default='data/output_data/tsc/sumo_colight_pytorch_agent/sumo7x28/test/dataset/data.mdb', type=str,
                        help='LMDB数据库路径（目录或data.mdb文件）')
    parser.add_argument('--all', action='store_true',
                        help='显示所有条目')
    parser.add_argument('-n', '--max-items', type=int, default=10,
                        help='最多显示的条目数, 默认: 10')
    parser.add_argument('-k', '--key', type=str,
                        help='搜索特定的键')
    parser.add_argument('--list-keys', action='store_true',
                        help='列出所有键')
    parser.add_argument('--pattern', type=str,
                        help='键名匹配模式（与--list-keys一起使用）')
    
    args = parser.parse_args()
    
    if args.list_keys:
        list_keys(args.db_path, args.pattern)
    else:
        read_lmdb(
            db_path=args.db_path,
            show_all=args.all,
            max_items=args.max_items,
            search_key=args.key
        )


if __name__ == '__main__':
    main()
